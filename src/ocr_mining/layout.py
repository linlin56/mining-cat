from dataclasses import dataclass, field

# A line taller than this ratio of its width is a vertical column (a single character is about square: either way).
VERTICAL_RATIO = 1.3
# Two lines of a block: the gap between them, relative to their thickness (column width, or line height)…
MAX_GAP_RATIO = 0.9
# …their thickness (font size) may differ by this factor (a bold or ruby line), not more…
MAX_SIZE_RATIO = 1.7
# …and they must overlap along the writing direction, by this share of the shorter one.
MIN_OVERLAP_RATIO = 0.2


@dataclass
class Line:
    text: str
    x: float  # pixels, top-left origin
    y: float
    w: float
    h: float

    @property
    def orientation(self) -> str:
        if self.h > self.w * VERTICAL_RATIO:
            return "vertical"
        if self.w > self.h * VERTICAL_RATIO:
            return "horizontal"
        return "square"

    @property
    def thickness(self) -> float:
        return self.w if self.orientation == "vertical" else self.h if self.orientation == "horizontal" else min(self.w, self.h)


@dataclass
class Block:
    lines: list[Line] = field(default_factory=list)
    vertical: bool = False

    @property
    def box(self) -> tuple[float, float, float, float]:
        x0 = min(l.x for l in self.lines)
        y0 = min(l.y for l in self.lines)
        x1 = max(l.x + l.w for l in self.lines)
        y1 = max(l.y + l.h for l in self.lines)
        return x0, y0, x1 - x0, y1 - y0


def _overlap(a0: float, a1: float, b0: float, b1: float) -> float:
    return min(a1, b1) - max(a0, b0)


def _direction(a: Line, b: Line) -> str | None:
    """The direction two lines are written in when they can be in the same block, else None."""
    kinds = {a.orientation, b.orientation} - {"square"}
    if len(kinds) > 1:
        return None
    return kinds.pop() if kinds else "either"


def _same_block(a: Line, b: Line) -> bool:
    direction = _direction(a, b)
    if direction is None:
        return False
    ta, tb = a.thickness, b.thickness
    if max(ta, tb) > MAX_SIZE_RATIO * min(ta, tb):
        return False
    thick = max(ta, tb)
    checks = ("vertical", "horizontal") if direction == "either" else (direction,)
    for d in checks:
        if d == "vertical":
            # columns side by side, sharing part of their height
            gap = -_overlap(a.x, a.x + a.w, b.x, b.x + b.w)
            along = _overlap(a.y, a.y + a.h, b.y, b.y + b.h)
            shorter = min(a.h, b.h)
        else:
            gap = -_overlap(a.y, a.y + a.h, b.y, b.y + b.h)
            along = _overlap(a.x, a.x + a.w, b.x, b.x + b.w)
            shorter = min(a.w, b.w)
        if gap <= MAX_GAP_RATIO * thick and along >= MIN_OVERLAP_RATIO * shorter:
            return True
    return False


def group_lines(lines: list[Line], right_to_left: bool = True) -> list[Block]:
    """Blocks of the page in reading order. `right_to_left`: manga order (columns and blocks read from the right)."""
    lines = [l for l in lines if l.text.strip() and l.w > 0 and l.h > 0]
    parent = list(range(len(lines)))

    def find(i: int) -> int:
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    for i in range(len(lines)):
        for j in range(i + 1, len(lines)):
            if _same_block(lines[i], lines[j]):
                parent[find(i)] = find(j)

    groups: dict[int, list[Line]] = {}
    for i, line in enumerate(lines):
        groups.setdefault(find(i), []).append(line)

    blocks = []
    for members in groups.values():
        vertical = any(l.orientation == "vertical" for l in members) or (
            len(members) > 1 and all(l.orientation == "square" for l in members) and _columns(members))
        if vertical:
            members.sort(key=lambda l: -(l.x + l.w / 2) if right_to_left else l.x + l.w / 2)
        else:
            members.sort(key=lambda l: (l.y + l.h / 2, l.x))
        blocks.append(Block(lines=members, vertical=vertical))
    return sort_blocks(blocks, right_to_left)


def _columns(lines: list[Line]) -> bool:
    """Square lines (one character each) stacked side by side rather than one under the other."""
    xs = [l.x + l.w / 2 for l in lines]
    ys = [l.y + l.h / 2 for l in lines]
    return max(xs) - min(xs) > max(ys) - min(ys)


def sort_blocks(blocks: list[Block], right_to_left: bool) -> list[Block]:
    """Reading order: rows of blocks from the top (blocks whose tops are close share a row), each row from the
    right in manga, from the left otherwise."""
    if not blocks:
        return []
    heights = sorted(b.box[3] for b in blocks)
    row_height = heights[len(heights) // 2] / 2  # half the median block height
    ordered = sorted(blocks, key=lambda b: b.box[1])
    rows: list[list[Block]] = []
    for block in ordered:
        if rows and block.box[1] - rows[-1][0].box[1] <= row_height:
            rows[-1].append(block)
        else:
            rows.append([block])
    result = []
    for row in rows:
        row.sort(key=lambda b: -(b.box[0] + b.box[2]) if right_to_left else b.box[0])
        result.extend(row)
    return result


def block_text(block: Block, no_space: bool) -> str:
    separator = "" if no_space else " "
    return separator.join(l.text.strip() for l in block.lines)


def to_json(blocks: list[Block], width: int, height: int, no_space: bool) -> list[dict]:
    """Blocks with their boxes as fractions of the page (the viewer scales them to the page as shown)."""
    def frac(x, y, w, h):
        return [round(x / width, 5), round(y / height, 5), round(w / width, 5), round(h / height, 5)]

    return [{
        "box": frac(*b.box),
        "vertical": b.vertical,
        "text": block_text(b, no_space),
        "lines": [{"text": l.text.strip(), "box": frac(l.x, l.y, l.w, l.h)} for l in b.lines],
    } for b in blocks]
