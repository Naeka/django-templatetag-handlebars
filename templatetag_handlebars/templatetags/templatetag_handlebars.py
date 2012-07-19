from django import template
from django.conf import settings
from django.template import Variable, TemplateSyntaxError


register = template.Library()


"""
From django-meio-easytags
https://github.com/vbmendes/django-meio-easytags/blob/master/src/easytags/node.py
"""

is_kwarg = lambda bit: not bit[0] in (u'"', u"'") and u'=' in bit


def get_args_kwargs_from_bits(parser, bits):
    args = []
    kwargs = {}
    for bit in bits:
        if is_kwarg(bit):
            key, value = bit.split(u'=', 1)
            kwargs[key] = parser.compile_filter(value)
        else:
            if not kwargs:
                args.append(parser.compile_filter(bit))
            else:
                raise TemplateSyntaxError(u"Args must be before kwargs.")

    return {'args': tuple(args), 'kwargs': kwargs}


def SmartVariable(var):
    if hasattr(var, 'resolve'):
        return var
    return Variable(var)


"""
    Most of this code was written by Miguel Araujo
    https://gist.github.com/893408
"""


def verbatim_tags(parser, token, endtagname):
    """
    Javascript templates (jquery, handlebars.js, mustache.js) use constructs like:

    ::

        {{if condition}} print something{{/if}}

    This, of course, completely screws up Django templates,
    because Django thinks {{ and }} means something.

    The following code preserves {{ }} tokens.

    This version of verbatim template tag allows you to use tags
    like url {% url name %}. {% trans "foo" %} or {% csrf_token %} within.
    """
    text_and_nodes = []
    while 1:
        token = parser.tokens.pop(0)
        if token.contents == endtagname:
            break

        if token.token_type == template.TOKEN_VAR:
            text_and_nodes.append('{{')
            text_and_nodes.append(token.contents)

        elif token.token_type == template.TOKEN_TEXT:
            text_and_nodes.append(token.contents)

        elif token.token_type == template.TOKEN_BLOCK:
            try:
                command = token.contents.split()[0]
            except IndexError:
                parser.empty_block_tag(token)

            try:
                compile_func = parser.tags[command]
            except KeyError:
                parser.invalid_block_tag(token, command, None)
            try:
                node = compile_func(parser, token)
            except template.TemplateSyntaxError, e:
                if not parser.compile_function_error(token, e):
                    raise
            text_and_nodes.append(node)

        if token.token_type == template.TOKEN_VAR:
            text_and_nodes.append('}}')

    return text_and_nodes


class VerbatimNode(template.Node):
    """
    Wrap {% verbatim %} and {% endverbatim %} around a
    block of javascript template and this will try its best
    to output the contents with no changes.

    ::

        {% verbatim %}
            {% trans "Your name is" %} {{first}} {{last}}
        {% endverbatim %}
    """
    def __init__(self, text_and_nodes):
        self.text_and_nodes = text_and_nodes

    def render(self, context):
        output = ""
        # If its text we concatenate it, otherwise it's a node and we render it
        for bit in self.text_and_nodes:
            if isinstance(bit, basestring):
                output += bit
            else:
                output += bit.render(context)
        return output


@register.tag
def verbatim(parser, token):
    text_and_nodes = verbatim_tags(parser, token, 'endverbatim')
    return VerbatimNode(text_and_nodes)


@register.simple_tag
def handlebars_js():
    return """<script src="%shandlebars.js"></script>""" % settings.STATIC_URL


class HandlebarsNode(VerbatimNode):
    """
    A Handlebars.js block is a *verbatim* block wrapped inside a
    named (``template_id``) <script> tag.

    ::

        {% tplhandlebars "tpl-popup" %}
            {{#ranges}}
                <li>{{min}} < {{max}}</li>
            {{/ranges}}
        {% endtplhandlebars %}

    """
    def __init__(self, text_and_nodes, template_name=None, template_id=None, **kwargs):
        super(HandlebarsNode, self).__init__(text_and_nodes)
        self.template_id = template_id
        self.template_name = template_name
        self.extended_args = kwargs

    def render(self, context):
        output = super(HandlebarsNode, self).render(context)
        attrs = []
        if self.template_id:
            attrs.append('id=%s' % self.template_id)
        if self.template_name:
            attrs.append('data-template-name=%s' % self.template_name)
        for arg, val in self.extended_args.items():
            attrs.append('%s=%s' % (arg, val))
        return """<script %s type="text/x-handlebars-template">%s</script>""" % (' '.join(attrs), output)


@register.tag
def tplhandlebars(parser, token):
    text_and_nodes = verbatim_tags(parser, token, endtagname='endtplhandlebars')
    bits = token.split_contents()
    args_kwargs = get_args_kwargs_from_bits(parser, bits[1:])
    args_kwargs['args'] = (text_and_nodes,) + args_kwargs['args']
    return HandlebarsNode(*args_kwargs['args'], **args_kwargs['kwargs'])
