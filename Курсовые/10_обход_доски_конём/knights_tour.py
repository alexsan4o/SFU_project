#!/usr/bin/env python3
"""Поиск гамильтонова пути коня на прямоугольной шахматной доске.

Пример: python knights_tour.py --rows 8 --cols 8 --start-row 1 --start-col 1
"""

from __future__ import annotations

import argparse
from collections.abc import Sequence

Position = tuple[int, int]

# Все восемь возможных ходов коня.
KNIGHT_MOVES: tuple[Position, ...] = (
    (2, 1),
    (1, 2),
    (-1, 2),
    (-2, 1),
    (-2, -1),
    (-1, -2),
    (1, -2),
    (2, -1),
)


def _build_adjacency(rows: int, cols: int) -> list[list[int]]:
    """Строит граф доски: клетка — вершина, ход коня — ребро."""
    adjacency: list[list[int]] = [[] for _ in range(rows * cols)]
    for row in range(rows):
        for col in range(cols):
            vertex = row * cols + col
            for row_delta, col_delta in KNIGHT_MOVES:
                next_row = row + row_delta
                next_col = col + col_delta
                if 0 <= next_row < rows and 0 <= next_col < cols:
                    adjacency[vertex].append(next_row * cols + next_col)
    return adjacency


def solve_tour(
    rows: int = 8,
    cols: int = 8,
    start: Position = (0, 0),
    *,
    closed: bool = False,
) -> list[Position] | None:
    """Находит обход доски конём или возвращает None, если обход не найден.

    Args:
        rows: количество строк доски.
        cols: количество столбцов доски.
        start: начальная клетка в координатах с нуля (строка, столбец).
        closed: если True, требует возвращения последним ходом в начальную
            клетку (замкнутый обход).

    Используется полный поиск с возвратом. Правило Варнсдорфа задаёт порядок
    перебора: сначала рассматриваются клетки с наименьшим числом дальнейших
    ходов. Это эвристика порядка, а не жадный выбор, поэтому полнота поиска
    сохраняется. Поиск реализован итеративно, чтобы не зависеть от лимита
    глубины рекурсии Python.
    """
    if rows <= 0 or cols <= 0:
        raise ValueError("Размеры доски должны быть положительными.")
    if len(start) != 2:
        raise ValueError("Начальная позиция должна состоять из двух координат.")
    start_row, start_col = start
    if not (0 <= start_row < rows and 0 <= start_col < cols):
        raise ValueError("Начальная клетка находится за пределами доски.")

    cell_count = rows * cols
    start_vertex = start_row * cols + start_col
    if cell_count == 1:
        # Открытый обход из одной клетки уже посещает всю доску.
        return None if closed else [start]

    adjacency = _build_adjacency(rows, cols)
    visited = [False] * cell_count
    visited[start_vertex] = True
    path = [start_vertex]

    def ordered_moves(vertex: int) -> list[int]:
        # При равенстве степеней сохраняется исходный детерминированный порядок.
        candidates = [neighbor for neighbor in adjacency[vertex] if not visited[neighbor]]
        candidates.sort(
            key=lambda neighbor: sum(
                not visited[next_vertex] for next_vertex in adjacency[neighbor]
            )
        )
        return candidates

    # Каждый элемент стека — список ходов для текущей клетки и индекс
    # следующего хода, который ещё нужно попробовать.
    frames: list[tuple[list[int], int]] = [(ordered_moves(start_vertex), 0)]

    while frames:
        candidates, next_index = frames[-1]
        if next_index == len(candidates):
            frames.pop()
            last_vertex = path.pop()
            visited[last_vertex] = False
            continue

        next_vertex = candidates[next_index]
        frames[-1] = (candidates, next_index + 1)
        if visited[next_vertex]:
            continue

        visited[next_vertex] = True
        path.append(next_vertex)

        if len(path) == cell_count:
            if not closed or start_vertex in adjacency[next_vertex]:
                return [(vertex // cols, vertex % cols) for vertex in path]
            # Для замкнутого обхода последний ход должен вести в начало.
            path.pop()
            visited[next_vertex] = False
            continue

        frames.append((ordered_moves(next_vertex), 0))

    return None


def format_board(rows: int, cols: int, tour: Sequence[Position]) -> str:
    """Форматирует маршрут как доску с порядковыми номерами ходов."""
    board = [[0] * cols for _ in range(rows)]
    for step, (row, col) in enumerate(tour, start=1):
        board[row][col] = step
    width = len(str(rows * cols))
    return "\n".join(" ".join(f"{value:0{width}d}" for value in row) for row in board)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Построить обход прямоугольной доски конём без повторных посещений."
    )
    parser.add_argument("--rows", type=int, default=8, help="число строк (по умолчанию 8)")
    parser.add_argument("--cols", type=int, default=8, help="число столбцов (по умолчанию 8)")
    parser.add_argument(
        "--start-row", type=int, default=1,
        help="строка старта, нумерация с 1 (по умолчанию 1)",
    )
    parser.add_argument(
        "--start-col", type=int, default=1,
        help="столбец старта, нумерация с 1 (по умолчанию 1)",
    )
    parser.add_argument(
        "--closed", action="store_true",
        help="искать замкнутый обход с возвратом в начальную клетку",
    )
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    try:
        tour = solve_tour(
            args.rows,
            args.cols,
            (args.start_row - 1, args.start_col - 1),
            closed=args.closed,
        )
    except ValueError as error:
        print(f"Ошибка: {error}")
        return 2

    if tour is None:
        print("Обход для заданной доски и начальной клетки не найден.")
        return 1

    print(format_board(args.rows, args.cols, tour))
    print(f"\nОбход найден: {len(tour)} клеток.")
    if args.closed:
        print("Маршрут замкнут: конь может вернуться в начальную клетку.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
