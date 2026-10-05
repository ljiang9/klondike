"""klondike: 终端 Klondike（经典接龙）纸牌游戏。

纯标准库实现。玩法:
- 7 列 tableau（工作区），4 个 foundation（目标区，按花色 A->K），stock/waste（牌堆/废牌堆）
- 每次从 stock 翻 1 张到 waste（draw 1 模式；用完后废牌堆回收重洗 stock）
- 移动命令:
    w        从 stock 翻一张到 waste
    w f1     waste 顶牌 -> foundation 1
    3 f2     tableau 第 3 列顶牌 -> foundation 2
    3 5      tableau 第 3 列顶牌(可带一串) -> tableau 第 5 列
    w 3      waste 顶牌 -> tableau 第 3 列
    u        悔棋（一步）
    q        退出
- 规则: tableau 内必须降序且红黑交替，空列只能放 K；
  foundation 按花色从 A 升序到 K。
- 胜利: 4 个 foundation 各 13 张牌。
"""
import argparse
import copy
import random
import secrets
import sys

SUITS = ["♠", "♥", "♦", "♣"]
RED = {"♥", "♦"}
RANKS = ["A", "2", "3", "4", "5", "6", "7", "8", "9", "10", "J", "Q", "K"]
RANK_VALUE = {r: i + 1 for i, r in enumerate(RANKS)}


def new_deck():
    return [(r, s) for s in SUITS for r in RANKS]


def card_name(card):
    r, s = card
    return f"{s}{r}"


def is_red(card):
    return card[1] in RED


def can_stack_tableau(card, dest_top):
    """tableau 堆叠规则: 空列只能放 K；否则降序红黑交替。"""
    if dest_top is None:
        return card[0] == "K"
    return (RANK_VALUE[card[0]] == RANK_VALUE[dest_top[0]] - 1
            and is_red(card) != is_red(dest_top))


def can_stack_foundation(card, pile):
    """foundation 规则: 空堆只能放 A；否则同花色升序。"""
    if not pile:
        return card[0] == "A"
    top = pile[-1]
    return card[1] == top[1] and RANK_VALUE[card[0]] == RANK_VALUE[top[0]] + 1


class Game:
    def __init__(self, seed=None):
        rng = random.Random(seed) if seed is not None else secrets.SystemRandom()
        deck = new_deck()
        rng.shuffle(deck)
        self.tableau = []   # 每列: list[card]，前部 face-down，用 face_up 计数
        self.face_up = []
        for col in range(7):
            pile = [deck.pop() for _ in range(col + 1)]
            self.tableau.append(pile)
            self.face_up.append(1)
        self.stock = deck          # 24 张
        self.waste = []
        self.foundations = [[], [], [], []]
        self.moves = 0
        self._history = []

    # ---- 快照/悔棋 ----
    def _snapshot(self):
        return (copy.deepcopy(self.tableau), list(self.face_up),
                list(self.stock), list(self.waste),
                copy.deepcopy(self.foundations), self.moves)

    def _restore(self, snap):
        (self.tableau, self.face_up, self.stock, self.waste,
         self.foundations, self.moves) = snap

    def _flip_if_needed(self, col):
        if self.face_up[col] == 0 and self.tableau[col]:
            self.face_up[col] = 1

    # ---- 操作 ----
    def draw(self):
        """从 stock 翻一张到 waste；stock 空则回收 waste。"""
        self._history.append(self._snapshot())
        if not self.stock:
            if not self.waste:
                self._history.pop()
                return False
            self.stock = list(reversed(self.waste))
            self.waste = []
            return True
        self.waste.append(self.stock.pop())
        self.moves += 1
        return True

    def _take_waste(self):
        if not self.waste:
            return None
        return self.waste[-1]

    def _take_tableau(self, col):
        if self.face_up[col] == 0:
            return None
        return self.tableau[col][-1]

    def move_waste_to_foundation(self, f):
        card = self._take_waste()
        if card is None or not can_stack_foundation(card, self.foundations[f]):
            return False
        self._history.append(self._snapshot())
        self.foundations[f].append(self.waste.pop())
        self.moves += 1
        return True

    def move_tableau_to_foundation(self, col, f):
        card = self._take_tableau(col)
        if card is None or not can_stack_foundation(card, self.foundations[f]):
            return False
        self._history.append(self._snapshot())
        self.foundations[f].append(self.tableau[col].pop())
        self.face_up[col] -= 1
        self._flip_if_needed(col)
        self.moves += 1
        return True

    def _tableau_sequence(self, col, n=1):
        """取第 col 列顶部 n 张（必须全 face-up 且内部合法）。"""
        pile = self.tableau[col]
        if self.face_up[col] < n or n < 1:
            return None
        seq = pile[-n:]
        for a, b in zip(seq, seq[1:]):
            if not (RANK_VALUE[b[0]] == RANK_VALUE[a[0]] - 1
                    and is_red(a) != is_red(b)):
                return None
        return seq

    def move_tableau_to_tableau(self, src, dst, n=1):
        if src == dst:
            return False
        seq = self._tableau_sequence(src, n)
        if seq is None:
            return False
        dest_top = self.tableau[dst][-1] if self.tableau[dst] else None
        if not can_stack_tableau(seq[0], dest_top):
            return False
        self._history.append(self._snapshot())
        del self.tableau[src][-n:]
        self.face_up[src] -= n
        self.tableau[dst].extend(seq)
        self._flip_if_needed(src)
        self.moves += 1
        return True

    def move_waste_to_tableau(self, dst):
        card = self._take_waste()
        if card is None:
            return False
        dest_top = self.tableau[dst][-1] if self.tableau[dst] else None
        if not can_stack_tableau(card, dest_top):
            return False
        self._history.append(self._snapshot())
        self.tableau[dst].append(self.waste.pop())
        self.moves += 1
        return True

    def undo(self):
        if not self._history:
            return False
        self._restore(self._history.pop())
        return True

    def won(self):
        return all(len(p) == 13 for p in self.foundations)

    # ---- 自动 bot（验证用，策略很弱） ----
    def legal_moves(self):
        mv = []
        if self.stock or self.waste:
            mv.append(("draw",))
        if self.waste:
            for f in range(4):
                if can_stack_foundation(self.waste[-1], self.foundations[f]):
                    mv.append(("w2f", f))
        for c in range(7):
            card = self._take_tableau(c)
            if card is None:
                continue
            for f in range(4):
                if can_stack_foundation(card, self.foundations[f]):
                    mv.append(("t2f", c, f))
            for d in range(7):
                if d == c:
                    continue
                dest_top = self.tableau[d][-1] if self.tableau[d] else None
                if can_stack_tableau(card, dest_top):
                    mv.append(("t2t", c, d, 1))
            if self.waste:
                dest_top = self.tableau[c][-1] if self.tableau[c] else None
                if can_stack_tableau(self.waste[-1], dest_top):
                    mv.append(("w2t", c))
        return mv

    def auto_step(self, rng):
        mv = self.legal_moves()
        if not mv:
            return False
        # 优先 foundation，其次 tableau 移动，最后翻牌
        for kind in ("w2f", "t2f", "w2t", "t2t", "draw"):
            cands = [m for m in mv if m[0] == kind]
            if cands:
                m = rng.choice(cands)
                return self._apply(m)
        return False

    def _apply(self, m):
        if m[0] == "draw":
            return self.draw()
        if m[0] == "w2f":
            return self.move_waste_to_foundation(m[1])
        if m[0] == "t2f":
            return self.move_tableau_to_foundation(m[1], m[2])
        if m[0] == "t2t":
            return self.move_tableau_to_tableau(m[1], m[2], m[3])
        if m[0] == "w2t":
            return self.move_waste_to_tableau(m[1])
        return False


def render(g):
    lines = []
    lines.append("stock:%d  waste:%s" % (
        len(g.stock), card_name(g.waste[-1]) if g.waste else "--"))
    lines.append(" ".join("f%d:%s" % (i + 1, card_name(p[-1]) if p else "--")
                          for i, p in enumerate(g.foundations)))
    lines.append("-" * 40)
    height = max(len(p) for p in g.tableau)
    for row in range(height):
        cells = []
        for c in range(7):
            pile = g.tableau[c]
            if row < len(pile):
                idx = row
                shown_up = idx >= len(pile) - g.face_up[c]
                cells.append(card_name(pile[idx]) if shown_up else "##")
            else:
                cells.append("  ")
        lines.append(" ".join("%-4s" % x for x in cells))
    lines.append(" ".join(" t%d " % (i + 1) for i in range(7)))
    return "\n".join(lines)


def _col(tok):
    """'3' -> 2 (0-based), 'f1' -> ('f', 0)。"""
    t = tok.lower()
    if t.startswith("f"):
        try:
            return ("f", int(t[1:]) - 1)
        except ValueError:
            return None
    try:
        return ("t", int(t) - 1)
    except ValueError:
        return None


def parse_command(text):
    """解析命令。返回 (ok, parsed)。parsed 为 'quit' 时退出。"""
    parts = text.strip().split()
    if not parts:
        return True, ""
    cmd = parts[0].lower()
    if cmd in ("q", "quit", "\u9000\u51fa"):
        return True, "quit"
    if cmd == "u":
        return True, "undo"
    if cmd == "h":
        return True, "help"
    if cmd == "w":
        if len(parts) == 1:
            return True, "draw"
        if len(parts) == 2:
            dst = _col(parts[1])
            if dst is None:
                return False, "\u547d\u4ee4\u4e0d\u8ba4\u8bc6\uff0c\u8f93\u5165 h \u770b\u5e2e\u52a9"
            if dst[0] == "f":
                return True, ("w2f", dst[1])
            return True, ("w2t", dst[1])
        return False, "\u547d\u4ee4\u4e0d\u8ba4\u8bc6\uff0c\u8f93\u5165 h \u770b\u5e2e\u52a9"
    # tableau 列号开头: "3 f2" / "3 5" / "3 2 5"
    src_c = _col(parts[0])
    if src_c is None or src_c[0] != "t":
        return False, "\u547d\u4ee4\u4e0d\u8ba4\u8bc6\uff0c\u8f93\u5165 h \u770b\u5e2e\u52a9"
    src = src_c[1]
    if not (0 <= src < 7):
        return False, "\u5217\u53f7\u5fc5\u987b 1-7"
    rest = parts[1:]
    n = 1
    # "3 2 5": 中间数字是张数; "3 5": 只有目标列
    if len(rest) == 2 and rest[0].isdigit():
        n = int(rest[0])
        rest = rest[1:]
    if len(rest) != 1:
        return False, "\u547d\u4ee4\u4e0d\u8ba4\u8bc6\uff0c\u8f93\u5165 h \u770b\u5e2e\u52a9"
    dst = _col(rest[0])
    if dst is None:
        return False, "\u547d\u4ee4\u4e0d\u8ba4\u8bc6\uff0c\u8f93\u5165 h \u770b\u5e2e\u52a9"
    if dst[0] == "f":
        if not (0 <= dst[1] < 4):
            return False, "\u76ee\u6807\u533a\u53f7\u5fc5\u987b 1-4"
        return True, ("t2f", src, dst[1])
    if not (0 <= dst[1] < 7):
        return False, "\u5217\u53f7\u5fc5\u987b 1-7"
    return True, ("t2t", src, dst[1], n)


HELP = """命令:
  w            从牌堆翻一张
  w f1         废牌堆顶 -> 目标区 1
  3 f2         第 3 列顶牌 -> 目标区 2
  3 5          第 3 列顶牌 -> 第 5 列
  3 2 5        第 3 列顶 2 张 -> 第 5 列
  w 3          废牌堆顶 -> 第 3 列
  u            悔棋一步
  q            退出"""


def apply_parsed(g, parsed):
    if parsed == "draw":
        return g.draw(), "已翻牌"
    if parsed == "undo":
        return g.undo(), "已悔棋" if True else "无可悔棋"
    if parsed == "help":
        return True, HELP
    if isinstance(parsed, tuple):
        kind = parsed[0]
        if kind == "w2f":
            ok = g.move_waste_to_foundation(parsed[1])
        elif kind == "t2f":
            ok = g.move_tableau_to_foundation(parsed[1], parsed[2])
        elif kind == "t2t":
            ok = g.move_tableau_to_tableau(parsed[1], parsed[2], parsed[3])
        elif kind == "w2t":
            ok = g.move_waste_to_tableau(parsed[1])
        else:
            return False, "内部错误"
        return ok, "已移动" if ok else "非法移动"
    return False, "内部错误"


def play_interactive(seed):
    g = Game(seed=seed)
    print("Klondike 接龙 | 输入 h 看帮助，q 退出")
    while True:
        print(render(g))
        if g.won():
            print("🎉 胜利！共用 %d 步。" % g.moves)
            return
        try:
            text = input("> ")
        except EOFError:
            print()
            return
        ok, parsed = parse_command(text)
        if parsed == "quit":
            print("已退出，共 %d 步。" % g.moves)
            return
        if not ok:
            print(parsed)
            continue
        done, msg = apply_parsed(g, parsed)
        if msg:
            print(msg)
        if not done and parsed not in ("help",):
            pass


def main(argv=None):
    ap = argparse.ArgumentParser(prog="klondike", description="终端 Klondike 接龙")
    ap.add_argument("--seed", type=int, default=None, help="随机种子")
    ap.add_argument("--auto", type=int, default=0, metavar="N",
                    help="自动 bot 走 N 步后退出（验证用）")
    args = ap.parse_args(argv)
    if args.auto > 0:
        g = Game(seed=args.seed)
        rng = random.Random(args.seed)
        steps = 0
        for _ in range(args.auto):
            if g.won() or not g.auto_step(rng):
                break
            steps += 1
        print("auto: 走了 %d 步, 胜利=%s, moves=%d" % (steps, g.won(), g.moves))
        return 0
    if not sys.stdin.isatty():
        print("error: 交互模式需要终端；管道场景请用 --auto", file=sys.stderr)
        return 2
    play_interactive(args.seed)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
