import unittest

from knights_tour import solve_tour


class KnightsTourTests(unittest.TestCase):
    @staticmethod
    def assert_valid_tour(test: unittest.TestCase, tour, rows: int, cols: int) -> None:
        test.assertIsNotNone(tour)
        assert tour is not None
        test.assertEqual(len(tour), rows * cols)
        test.assertEqual(len(set(tour)), rows * cols)
        test.assertTrue(all(0 <= row < rows and 0 <= col < cols for row, col in tour))
        for (row_a, col_a), (row_b, col_b) in zip(tour, tour[1:]):
            test.assertEqual(
                sorted((abs(row_b - row_a), abs(col_b - col_a))),
                [1, 2],
            )

    def test_finds_open_tour_on_standard_board(self) -> None:
        tour = solve_tour()
        self.assert_valid_tour(self, tour, 8, 8)
        self.assertEqual(tour[0], (0, 0))

    def test_finds_closed_tour_when_requested(self) -> None:
        tour = solve_tour(8, 8, (0, 0), closed=True)
        self.assert_valid_tour(self, tour, 8, 8)
        assert tour is not None
        row_a, col_a = tour[-1]
        row_b, col_b = tour[0]
        self.assertEqual(sorted((abs(row_b - row_a), abs(col_b - col_a))), [1, 2])

    def test_single_cell_is_an_open_tour(self) -> None:
        self.assertEqual(solve_tour(1, 1), [(0, 0)])

    def test_returns_none_if_no_open_tour_exists(self) -> None:
        self.assertIsNone(solve_tour(2, 3))

    def test_rejects_non_positive_board_size(self) -> None:
        with self.assertRaises(ValueError):
            solve_tour(0, 8)

    def test_rejects_start_outside_board(self) -> None:
        with self.assertRaises(ValueError):
            solve_tour(8, 8, (8, 0))


if __name__ == "__main__":
    unittest.main()
