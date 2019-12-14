from typing import cast

from ...error import GraphQLError
from ...language import (
    BooleanValueNode,
    EnumValueNode,
    FloatValueNode,
    IntValueNode,
    NullValueNode,
    ListValueNode,
    ObjectFieldNode,
    ObjectValueNode,
    StringValueNode,
    ValueNode,
    print_ast,
)
from ...pyutils import did_you_mean, is_invalid, suggestion_list
from ...type import (
    GraphQLScalarType,
    get_named_type,
    get_nullable_type,
    is_enum_type,
    is_input_object_type,
    is_list_type,
    is_non_null_type,
    is_required_input_field,
    is_scalar_type,
)
from . import ValidationRule

__all__ = ["ValuesOfCorrectTypeRule"]


class ValuesOfCorrectTypeRule(ValidationRule):
    """Value literals of correct type

    A GraphQL document is only valid if all value literals are of the type expected at
    their position.
    """

    def enter_list_value(self, node: ListValueNode, *_args):
        # Note: TypeInfo will traverse into a list's item type, so look to the parent
        # input type to check if it is a list.
        type_ = get_nullable_type(self.context.get_parent_input_type())
        if not is_list_type(type_):
            self.is_valid_value_node(node)
            return self.SKIP  # Don't traverse further.

    def enter_object_value(self, node: ObjectValueNode, *_args):
        type_ = get_named_type(self.context.get_input_type())
        if not is_input_object_type(type_):
            self.is_valid_value_node(node)
            return self.SKIP  # Don't traverse further.
        # Ensure every required field exists.
        field_node_map = {field.name.value: field for field in node.fields}
        for field_name, field_def in type_.fields.items():
            field_node = field_node_map.get(field_name)
            if not field_node and is_required_input_field(field_def):
                field_type = field_def.type
                self.report_error(
                    GraphQLError(
                        f"Field '{type_.name}.{field_name}' of required type"
                        f" '{field_type}' was not provided.",
                        node,
                    )
                )

    def enter_object_field(self, node: ObjectFieldNode, *_args):
        parent_type = get_named_type(self.context.get_parent_input_type())
        field_type = self.context.get_input_type()
        if not field_type and is_input_object_type(parent_type):
            suggestions = suggestion_list(node.name.value, list(parent_type.fields))
            self.report_error(
                GraphQLError(
                    f"Field '{node.name.value}'"
                    f" is not defined by type '{parent_type.name}'."
                    + did_you_mean(suggestions),
                    node,
                )
            )

    def enter_null_value(self, node: NullValueNode, *_args):
        type_ = self.context.get_input_type()
        if is_non_null_type(type_):
            self.report_error(
                GraphQLError(
                    f"Expected value of type '{type_}', found {print_ast(node)}.", node
                )
            )

    def enter_enum_value(self, node: EnumValueNode, *_args):
        self.is_valid_value_node(node)

    def enter_int_value(self, node: IntValueNode, *_args):
        self.is_valid_value_node(node)

    def enter_float_value(self, node: FloatValueNode, *_args):
        self.is_valid_value_node(node)

    def enter_string_value(self, node: StringValueNode, *_args):
        self.is_valid_value_node(node)

    def enter_boolean_value(self, node: BooleanValueNode, *_args):
        self.is_valid_value_node(node)

    def is_valid_value_node(self, node: ValueNode) -> None:
        """Check whether this is a valid value node.

        Any value literal may be a valid representation of a Scalar, depending on that
        scalar type.
        """
        # Report any error at the full type expected by the location.
        location_type = self.context.get_input_type()
        if not location_type:
            return

        type_ = get_named_type(location_type)

        if is_enum_type(type_):
            if not isinstance(node, EnumValueNode) or node.value not in type_.values:
                all_names = list(type_.values)
                suggested_values = suggestion_list(print_ast(node), all_names)
                self.report_error(
                    GraphQLError(
                        f"Expected value of type '{type_.name}',"
                        f" found {print_ast(node)}."
                        + did_you_mean(suggested_values, "the enum value"),
                        node,
                    )
                )
            return

        if not is_scalar_type(type_):
            self.report_error(
                GraphQLError(
                    f"Expected value of type '{location_type}',"
                    f" found {print_ast(node)}.",
                    node,
                )
            )
            return

        # Scalars determine if a literal value is valid via `parse_literal()` which may
        # throw or return an invalid value to indicate failure.
        type_ = cast(GraphQLScalarType, type_)
        try:
            parse_result = type_.parse_literal(node)
            if is_invalid(parse_result):
                self.report_error(
                    GraphQLError(
                        f"Expected value of type '{location_type}',"
                        f" found {print_ast(node)}.",
                        node,
                    )
                )
        except Exception as error:
            # Ensure a reference to the original error is maintained.
            self.report_error(
                GraphQLError(
                    f"Expected value of type '{location_type}',"
                    f" found {print_ast(node)}; {error}",
                    node,
                    original_error=error,
                )
            )
