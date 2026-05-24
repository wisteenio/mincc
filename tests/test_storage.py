"""本地持久化存储测试。"""

from pathlib import PureWindowsPath

from mincc.storage import INPUT_HISTORY_TYPE, MinccStorage, project_id_from_path


def test_storage_archives_records_by_project_and_type(tmp_path) -> None:
    storage = MinccStorage.create(root=tmp_path, project_id="project-a")

    storage.append_input("first")
    storage.append_input("second")

    path = tmp_path / "projects" / "project-a" / INPUT_HISTORY_TYPE / "records.jsonl"
    assert path.exists()
    assert storage.read_inputs() == ["first", "second"]


def test_storage_ignores_invalid_jsonl_records(tmp_path) -> None:
    storage = MinccStorage.create(root=tmp_path, project_id="project-a")
    path = storage.records_path(INPUT_HISTORY_TYPE)
    path.parent.mkdir(parents=True)
    path.write_text('{"text": "ok"}\nnot-json\n{"text": ""}\n', encoding="utf-8")

    assert storage.read_inputs() == ["ok"]


def test_project_id_from_path_is_stable(tmp_path) -> None:
    project = tmp_path / "my project"
    project.mkdir()

    assert project_id_from_path(project) == project_id_from_path(project)
    assert project_id_from_path(project).endswith("my-project")


def test_project_id_from_path_reflects_full_path(tmp_path) -> None:
    project = tmp_path / "code" / "mincc"
    project.mkdir(parents=True)

    project_id = project_id_from_path(project)

    assert "code-mincc" in project_id
    assert project_id.endswith("code-mincc")


def test_project_id_from_path_keeps_chinese_names(tmp_path) -> None:
    project = tmp_path / "项目 甲"
    project.mkdir()

    assert project_id_from_path(project).endswith("项目-甲")


def test_project_id_from_path_supports_windows_paths() -> None:
    project = PureWindowsPath("C:/Users/yanglin/code/mincc")

    assert project_id_from_path(project) == "C-Users-yanglin-code-mincc"


def test_project_id_from_path_supports_unc_paths() -> None:
    project = PureWindowsPath("//server/share/code/mincc")

    assert project_id_from_path(project) == "server-share-code-mincc"


def test_project_id_from_path_limits_single_directory_name_length() -> None:
    project = PureWindowsPath("C:/Users/yanglin/code/" + "a" * 220)

    assert len(project_id_from_path(project)) <= 200
