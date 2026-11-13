"""Only associative AND regrouping in native PostgreSQL CHECK deparse tokens."""

MAX_GROUP_DEPTH = 64
CHECK_PREFIX = ["c", "|", "t", "|", "CHECK"]
UNSUPPORTED = frozenset({"CASE", "BETWEEN", "SELECT", "WITH", "UNION", "EXISTS", "OVER"})


class GroupingError(ValueError):
    """Unsupported or incomplete native token grouping, without definition text."""


def canonical_check(tokens: list[str]) -> list[str]:
    if tokens[: len(CHECK_PREFIX)] != CHECK_PREFIX or UNSUPPORTED.intersection(tokens):
        return tokens
    return groups(tokens)


def closing(tokens: list[str], start: int) -> int:
    depth = 0
    for index in range(start, len(tokens)):
        if tokens[index] == "(":
            depth += 1
        elif tokens[index] == ")":
            depth -= 1
            if depth == 0:
                return index
    raise GroupingError("check_group_incomplete")


def top_and(tokens: list[str]) -> tuple[int, ...]:
    depth = 0
    positions = []
    for index, symbol in enumerate(tokens):
        if symbol == "(":
            depth += 1
        elif symbol == ")":
            depth -= 1
            if depth < 0:
                raise GroupingError("check_group_incomplete")
        elif depth == 0:
            if symbol in {"OR", "NOT"}:
                return ()
            if symbol == "AND":
                positions.append(index)
    if depth:
        raise GroupingError("check_group_incomplete")
    return tuple(positions)


def flatten(tokens: list[str]) -> list[str]:
    positions = top_and(tokens)
    if not positions:
        return tokens
    starts = (0, *(index + 1 for index in positions))
    ends = (*positions, len(tokens))
    result: list[str] = []
    for start, end in zip(starts, ends, strict=True):
        operand = tokens[start:end]
        if not operand:
            raise GroupingError("check_and_operand")
        if operand[0] == "(" and closing(operand, 0) == len(operand) - 1 and top_and(operand[1:-1]):
            operand = operand[1:-1]
        if result:
            result.append("AND")
        result.extend(operand)
    return result


def groups(tokens: list[str], depth: int = 0) -> list[str]:
    if depth > MAX_GROUP_DEPTH:
        raise GroupingError("check_group_bound")
    result: list[str] = []
    index = 0
    while index < len(tokens):
        if tokens[index] == "(":
            end = closing(tokens, index)
            inner = groups(tokens[index + 1 : end], depth + 1)
            result.extend(["(", *flatten(inner), ")"])
            index = end + 1
        elif tokens[index] == ")":
            raise GroupingError("check_group_incomplete")
        else:
            result.append(tokens[index])
            index += 1
    return result
