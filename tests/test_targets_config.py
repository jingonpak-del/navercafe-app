from navercafe_app.config.targets import load_targets, parse_targets


def test_parse_targets_extracts_slug_and_menu_id():
    targets = parse_targets(
        {
            "defaults": {"max_pages_per_board": 2, "delay_seconds": {"min": 0, "max": 0}},
            "targets": [
                {
                    "name": "카페",
                    "cafe_url": "https://cafe.naver.com/mycafe?clubid=999",
                    "boards": [
                        {
                            "name": "게시판",
                            "board_url": "https://cafe.naver.com/ArticleList.nhn?search.clubid=999&search.menuid=12",
                        }
                    ],
                }
            ],
        }
    )
    assert targets.defaults.max_pages_per_board == 2
    assert targets.targets[0].cafe_slug == "mycafe"
    assert targets.targets[0].cafe_id == "999"
    assert targets.targets[0].boards[0].menu_id == "12"


def test_load_targets_yaml(tmp_path):
    path = tmp_path / "targets.yaml"
    path.write_text(
        """
        defaults:
          max_pages_per_board: 1
          include_comments: false
          delay_seconds:
            min: 0
            max: 0
        targets:
          - name: 샘플
            cafe_url: https://cafe.naver.com/sample
            cafe_id: '123'
            boards:
              - name: 자유
                menu_id: '7'
        """,
        encoding="utf-8",
    )
    targets = load_targets(path)
    assert targets.targets[0].name == "샘플"
    assert targets.targets[0].boards[0].menu_id == "7"
    assert targets.defaults.include_comments is False
