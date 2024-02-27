import builtins
from collections import namedtuple

from .. import grammars, objectmodel
from ..mixins.indent import IndentPrintMixin
from ..util import compress_seq, safe_name
from ..util.misc import topsort

HEADER = """\
    #!/usr/bin/env python3

    # WARNING: CAVEAT UTILITOR
    #
    # This file was automatically generated by TatSu.
    #
    #    https://pypi.python.org/pypi/tatsu/
    #
    # Any changes you make to it will be overwritten the next time
    # the file is generated.

    from __future__ import annotations

    from typing import Any
    from dataclasses import dataclass

    from tatsu.semantics import ModelBuilderSemantics
    {base_type_import}


    class {name}ModelBuilderSemantics(ModelBuilderSemantics):
        def __init__(self, context=None, types=None):
            types = [
                t for t in globals().values()
                if type(t) is type and issubclass(t, ModelBase)
            ] + (types or [])
            super().__init__(context=context, types=types)
"""


BaseClassSpec = namedtuple('BaseClassSpec', ['class_name', 'base'])


def modelgen(model: grammars.Grammar, name: str = '', base_type: type | None = objectmodel.Node) -> str:
    base_type = base_type or objectmodel.Node
    generator = PythonModelGenerator(name=name, base_type=base_type)
    return generator.generate_model(model)


class PythonModelGenerator(IndentPrintMixin):

    def __init__(self, name: str = '', base_type: type = objectmodel.Node):
        super().__init__()
        self.base_type = base_type
        self.name = name or None

    def generate_model(self, grammar: grammars.Grammar):
        base_type = self.base_type
        base_type_name = base_type.__name__.split('.')[-1]
        base_type_import = f"from {base_type.__module__} import {base_type_name}"

        self.name = self.name or grammar.name
        self.print(
            HEADER.format(
                name=self.name,
                base_type=self.base_type.__name__,
                base_type_import=base_type_import,
            ),
        )

        rule_index = {rule.name: rule for rule in grammar.rules}
        rule_specs = {
            rule.name: self._base_class_specs(rule)
            for rule in grammar.rules
        }
        rule_specs = {name: specs for name, specs in rule_specs.items() if specs}

        specs_by_name = {
            s.class_name: s.base
            for specs in rule_specs.values()
            for s in specs
        }
        base = self._model_base_name()
        specs_by_name[base] = base_type_name

        all_specs = {
            (s.class_name, s.base)
            for specs in rule_specs.values()
            for s in specs
        }
        model_names = topsort(reversed(specs_by_name), all_specs)

        model_to_rule = {
            rule_specs[name][0].class_name: rule
            for name, rule in rule_index.items()
            if name in rule_specs
        }

        for model_name in model_names:
            if model_name in vars(builtins):
                continue
            if rule := model_to_rule.get(model_name):
                self._gen_rule_class(rule, rule_specs[rule.name])
            else:
                self._gen_base_class(model_name, specs_by_name.get(model_name))

        return self.printed_text()

    @staticmethod
    def _model_base_name():
        return 'ModelBase'

    def _gen_base_class(self, class_name: str, base: str | None):
        self.print()
        self.print()
        self.print('@dataclass(eq=False)')
        if base:
            self.print(f'class {class_name}({base}):')
        else:
            # FIXME: this cannot happen as base_type is the final base
            self.print(f'class {class_name}:')
        with self.indent():
            self.print('pass')

    def _gen_rule_class(self, rule: grammars.Rule, specs: list[BaseClassSpec]):
        if not specs:
            return
        spec = specs[0]
        arguments = sorted({safe_name(d) for d, _ in compress_seq(rule.defines())})

        self.print()
        self.print()
        self.print('@dataclass(eq=False)')
        self.print(f'class {spec.class_name}({spec.base}):')
        with self.indent():
            if not arguments:
                self.print('pass')
            for arg in arguments:
                self.print(f'{arg}: Any = None')

    def _base_class_specs(self, rule: grammars.Rule) -> list[BaseClassSpec]:
        if not rule.params or not isinstance(rule.params[0], str):
            return []
        spec = rule.params[0].split('::')
        base = [self._model_base_name()]
        class_names = [safe_name(n) for n in spec] + base
        return [
            BaseClassSpec(class_name, class_names[i + 1])
            for i, class_name in enumerate(class_names[:-1])
        ]