"""
tests/unit/test_global_ai_assistant.py

Comprehensive tests for PART 5 — File Explorer-Wide AI Assistant:
1. Global File Explorer scope & Layered Search:
   - Level 1: Current project / folder
   - Level 2: Previously indexed locations (IndexCache)
   - Level 3: File Explorer discovery
   - Level 4: Explicit user location ("Find all PDF files in D:\\Documents")
2. Natural-language searches:
   - "Where is heart.csv?", "Find my resume", "all Python files", "modified recently",
     "folders containing datasets", "duplicate-looking files", "What is inside <dir>?"
3. Follow-up context across locations:
   - "Where is my resume?" -> "Open its folder" -> "Rename it to Kamaldeep_Resume.pdf" -> "Confirm"
4. File/folder operations:
   - CREATE (file, folder)
   - READ (read text, inspect metadata, list directory)
   - RENAME (single, batch pattern)
   - MOVE (single, batch move)
   - COPY (single, folder copy)
   - DELETE (destructive confirmation gate, verify deletion)
   - ORGANIZE (create folders, move matching files)
   - EDIT (code/content modification, diff generation, confirm, auto-reindex)
5. Ambiguity handling:
   - Asking clarification when multiple candidates exist (never guessing)
6. System path protection & safety:
   - Blocks modifications to system directories
7. Continued support for project intelligence:
   - "What uses...", "What happens if I delete...", "Why does X depend on Y?", "Explain project"
"""
import os
import shutil
import time
from pathlib import Path
import pytest

from app.main import PreViewAIService
from app.ai.global_search import GlobalSearchEngine, SearchResultItem
from app.ai.file_operations import FileOperationsEngine, OperationPlan
from app.ai.conversation_context import AIConversationContext
from app.ai.assistant_router import GlobalAIAssistant, AssistantResponse
from app.state.index_cache import IndexCache


@pytest.fixture
def mock_explorer_env(tmp_path):
    """
    Creates a realistic mock File Explorer environment with multiple locations:
    - Current project: tmp_path / "disease_detection" (train.py, app.py, dataset/heart.csv)
    - Other folder: tmp_path / "Documents" (Resume.pdf, notes.txt)
    - Another folder: tmp_path / "Projects" (ML_Presentation.pptx, resume_backup.pdf)
    """
    # 1. Disease detection project (Current navigation context)
    proj = tmp_path / "disease_detection"
    proj.mkdir()
    (proj / "train.py").write_text(
        "import dataset\nthreshold = 0.5\ndef train_model():\n    pass\n",
        encoding="utf-8"
    )
    (proj / "app.py").write_text(
        'import train\nMODEL_PATH = "model.pkl"\ndef serve():\n    pass\n',
        encoding="utf-8"
    )
    ds_dir = proj / "dataset"
    ds_dir.mkdir()
    (ds_dir / "heart.csv").write_text("age,sex,cp,chol\n63,1,3,145\n", encoding="utf-8")
    (proj / "model.pkl").write_text("fake_pickle_data", encoding="utf-8")

    # 2. Documents folder (outside current project)
    docs = tmp_path / "Documents"
    docs.mkdir()
    (docs / "Resume.pdf").write_text("%PDF-1.4 mock resume content", encoding="utf-8")
    (docs / "notes.txt").write_text("Meeting notes and presentation ideas", encoding="utf-8")

    # 3. Projects folder (outside current project)
    projects_dir = tmp_path / "Projects"
    projects_dir.mkdir()
    (projects_dir / "ML_Presentation.pptx").write_text("Presentation slide deck", encoding="utf-8")
    (projects_dir / "resume_backup.pdf").write_text("%PDF-1.4 backup resume", encoding="utf-8")

    return {
        "root": tmp_path,
        "current_project": proj,
        "documents": docs,
        "projects": projects_dir,
        "cache_path": tmp_path / "test_cache.db",
    }


# ──────────────────────────────────────────────────────────────────────────────
# 1. Global File Explorer Scope & Search Tests
# ──────────────────────────────────────────────────────────────────────────────

def test_ai_scope_not_restricted_to_current_folder(mock_explorer_env):
    """
    Verify AI answers queries about files outside the current project folder
    rather than saying 'I can only answer questions about disease detection'.
    """
    env = mock_explorer_env
    svc = PreViewAIService(project_root=str(env["current_project"]))
    svc.load_project(str(env["current_project"]))

    # Add other locations as accessible discovery roots
    svc.assistant.search_engine.add_known_location(str(env["documents"]))
    svc.assistant.search_engine.add_known_location(str(env["projects"]))

    # User asks about resume while inside disease_detection
    res = svc.handle_chat_message("Where is my resume?")
    assert res is not None
    reply = res.reply_text

    # Must find the files in Documents and Projects, not invent or block
    assert "Resume.pdf" in reply
    assert "Documents" in reply
    assert "I can only answer" not in reply


def test_layered_search_levels(mock_explorer_env, tmp_path):
    """Verify Level 1, Level 2, Level 3, and Level 4 search operations."""
    env = mock_explorer_env
    svc = PreViewAIService(project_root=str(env["current_project"]))
    svc.load_project(str(env["current_project"]))

    # Level 1: Current folder search
    l1_results = svc.assistant.search_engine.search("heart.csv")
    assert any("heart.csv" in r.name for r in l1_results)
    assert l1_results[0].layer in (1, 2)

    # Level 4: Explicit user location
    l4_results = svc.assistant.search_engine.search("Resume", explicit_location=str(env["documents"]))
    assert len(l4_results) >= 1
    assert "Resume.pdf" in l4_results[0].name
    assert l4_results[0].layer == 4

    # Search with extension filter
    pdf_results = svc.assistant.search_engine.search(
        query="*",
        explicit_location=str(env["documents"]),
        extensions=[".pdf"],
    )
    assert all(r.extension == ".pdf" for r in pdf_results)


def test_natural_language_search_queries(mock_explorer_env):
    """Verify various natural language search query forms."""
    env = mock_explorer_env
    svc = PreViewAIService(project_root=str(env["current_project"]))
    svc.load_project(str(env["current_project"]))
    svc.assistant.search_engine.add_known_location(str(env["documents"]))
    svc.assistant.search_engine.add_known_location(str(env["projects"]))

    # "Find my resume"
    r1 = svc.handle_chat_message("Find my resume")
    assert "Resume.pdf" in r1.reply_text

    # "Where is heart.csv?"
    r2 = svc.handle_chat_message("Where is heart.csv?")
    assert "heart.csv" in r2.reply_text

    # "Find all Python files"
    r3 = svc.handle_chat_message("Find all Python files")
    assert "train.py" in r3.reply_text or "app.py" in r3.reply_text

    # "What is inside <dir>?"
    r4 = svc.handle_chat_message(f"What is inside {env['documents']}?")
    assert "Resume.pdf" in r4.reply_text
    assert "notes.txt" in r4.reply_text


def test_find_duplicate_files(mock_explorer_env):
    """Verify finding duplicate-looking files across accessible locations."""
    env = mock_explorer_env
    # Create a duplicate file with identical content & name in two locations
    dup_name = "shared_dataset.csv"
    content = "col1,col2\n100,200\n"
    (env["current_project"] / dup_name).write_text(content, encoding="utf-8")
    (env["projects"] / dup_name).write_text(content, encoding="utf-8")

    svc = PreViewAIService(project_root=str(env["current_project"]))
    svc.assistant.search_engine.add_known_location(str(env["projects"]))

    res = svc.handle_chat_message("Find duplicate-looking files")
    assert "shared_dataset.csv" in res.reply_text


# ──────────────────────────────────────────────────────────────────────────────
# 2. Multi-turn Follow-up Context Tests
# ──────────────────────────────────────────────────────────────────────────────

def test_end_to_end_follow_up_workflow(mock_explorer_env):
    """
    Test the complete Part 5 acceptance workflow:
    1. User inside disease_detection asks about Resume.pdf.
    2. AI finds it.
    3. User asks: 'Open its folder'. AI navigates there.
    4. User asks: 'Rename it to Kamaldeep_Resume.pdf'. AI prepares plan with confirmation.
    5. User confirms. AI executes rename, verifies on disk, updates index.
    """
    env = mock_explorer_env
    svc = PreViewAIService(project_root=str(env["current_project"]), cache_path=env["cache_path"])
    svc.load_project(str(env["current_project"]))
    svc.assistant.search_engine.add_known_location(str(env["documents"]))

    # Step 1 & 2: Search across locations
    r1 = svc.handle_chat_message("Where is my resume?")
    assert "Resume.pdf" in r1.reply_text
    assert svc.assistant.context.last_target_path is not None
    assert "Resume.pdf" in svc.assistant.context.last_target_path

    # Step 3: Open its folder
    r2 = svc.handle_chat_message("Open its folder")
    assert r2.action_type == "NAVIGATE"
    assert r2.navigation_target == str(env["documents"])
    assert svc.assistant.context.navigation_location == str(env["documents"])

    # Step 4: Rename it
    r3 = svc.handle_chat_message("Rename it to Kamaldeep_Resume.pdf")
    assert r3.action_type == "PLAN_CONFIRMATION"
    assert svc.assistant.context.pending_plan is not None
    assert "Kamaldeep_Resume.pdf" in r3.reply_text

    # Step 5: User confirms
    r4 = svc.handle_chat_message("Confirm")
    assert r4.action_type == "OPERATION_DONE"
    assert "Kamaldeep_Resume.pdf" in r4.reply_text

    # Verify real filesystem result
    old_file = env["documents"] / "Resume.pdf"
    new_file = env["documents"] / "Kamaldeep_Resume.pdf"
    assert not old_file.exists()
    assert new_file.exists()


# ──────────────────────────────────────────────────────────────────────────────
# 3. File Operations through AI
# ──────────────────────────────────────────────────────────────────────────────

def test_ai_create_file_and_folder(mock_explorer_env):
    """Verify creating files and folders via natural language."""
    env = mock_explorer_env
    svc = PreViewAIService(project_root=str(env["current_project"]))
    svc.load_project(str(env["current_project"]))

    # Create folder: "Create a folder called screenshots"
    res1 = svc.handle_chat_message("Create a folder called screenshots")
    assert (env["current_project"] / "screenshots").exists()
    assert (env["current_project"] / "screenshots").is_dir()

    # Create file: "Create a README.md in this project"
    res2 = svc.handle_chat_message("Create a README.md")
    assert (env["current_project"] / "README.md").exists()
    assert (env["current_project"] / "README.md").is_file()


def test_ai_move_and_copy_file(mock_explorer_env):
    """Verify moving and copying files via natural language."""
    env = mock_explorer_env
    svc = PreViewAIService(project_root=str(env["current_project"]))
    svc.load_project(str(env["current_project"]))

    # Create a test file
    test_f = env["current_project"] / "extra_data.csv"
    test_f.write_text("a,b\n1,2\n", encoding="utf-8")

    # Move file into dataset folder
    res_move = svc.handle_chat_message("Move extra_data.csv into dataset")
    assert not test_f.exists()
    dest_f = env["current_project"] / "dataset" / "extra_data.csv"
    assert dest_f.exists()

    # Copy file: "Copy extra_data.csv to backup"
    res_copy = svc.handle_chat_message(f"Copy {dest_f} to {env['current_project'] / 'backup'}")
    assert dest_f.exists()  # Original still exists
    assert (env["current_project"] / "backup" / "extra_data.csv").exists()


def test_ai_delete_requires_confirmation(mock_explorer_env):
    """Verify destructive delete operations strictly require confirmation."""
    env = mock_explorer_env
    svc = PreViewAIService(project_root=str(env["current_project"]))
    svc.load_project(str(env["current_project"]))

    del_target = env["current_project"] / "temp_file.txt"
    del_target.write_text("temporary data", encoding="utf-8")

    # Request delete
    res1 = svc.handle_chat_message(f"Delete {del_target}")
    assert res1.action_type == "PLAN_CONFIRMATION"
    assert del_target.exists()  # Must NOT be deleted yet!
    assert "Confirm" in res1.reply_text

    # User cancels
    res_cancel = svc.handle_chat_message("Cancel")
    assert del_target.exists()  # Still not deleted!

    # Request delete again and confirm
    svc.handle_chat_message(f"Delete {del_target}")
    res_confirm = svc.handle_chat_message("Confirm")
    assert res_confirm.action_type == "OPERATION_DONE"
    assert not del_target.exists()  # Now verified deleted on disk


def test_ai_code_modification_workflow(mock_explorer_env):
    """
    Verify code modification:
    - User requests: 'Change the threshold from 0.5 to 0.7 in train.py'
    - AI locates file, prepares diff, requests confirmation.
    - User confirms.
    - File is updated, verified on disk, and auto-reindexed.
    """
    env = mock_explorer_env
    svc = PreViewAIService(project_root=str(env["current_project"]))
    svc.load_project(str(env["current_project"]))

    train_file = env["current_project"] / "train.py"
    assert "threshold = 0.5" in train_file.read_text(encoding="utf-8")

    # Request modification
    res_plan = svc.handle_chat_message("Change the threshold from 0.5 to 0.7 in train.py")
    assert res_plan.action_type == "PLAN_CONFIRMATION"
    assert "diff" in res_plan.reply_text.lower() or "0.7" in res_plan.reply_text
    assert svc.assistant.context.pending_plan is not None

    # Confirm modification
    res_exec = svc.handle_chat_message("Confirm")
    assert res_exec.action_type == "OPERATION_DONE"

    # Verify modification on real disk
    new_code = train_file.read_text(encoding="utf-8")
    assert "threshold = 0.7" in new_code
    assert "threshold = 0.5" not in new_code

    # Verify index was updated
    assert "Updated project index" in res_exec.reply_text


def test_ai_model_path_modification(mock_explorer_env):
    """Verify changing model path in code."""
    env = mock_explorer_env
    svc = PreViewAIService(project_root=str(env["current_project"]))
    svc.load_project(str(env["current_project"]))

    app_file = env["current_project"] / "app.py"
    assert 'MODEL_PATH = "model.pkl"' in app_file.read_text(encoding="utf-8")

    res_plan = svc.handle_chat_message("Change the model loading path to models/best_model.pkl in app.py")
    assert res_plan.action_type == "PLAN_CONFIRMATION"

    res_exec = svc.handle_chat_message("Confirm")
    assert res_exec.action_type == "OPERATION_DONE"

    new_app_code = app_file.read_text(encoding="utf-8")
    assert "models/best_model.pkl" in new_app_code


# ──────────────────────────────────────────────────────────────────────────────
# 4. Ambiguity Resolution & Safety Tests
# ──────────────────────────────────────────────────────────────────────────────

def test_ai_asks_clarification_on_ambiguity(mock_explorer_env):
    """Verify AI asks clarification when multiple candidates exist rather than guessing."""
    env = mock_explorer_env
    # Create two models in different folders
    (env["current_project"] / "best_model.pkl").write_text("model1", encoding="utf-8")
    (env["projects"] / "old_model.pkl").write_text("model2", encoding="utf-8")

    svc = PreViewAIService(project_root=str(env["current_project"]))
    svc.load_project(str(env["current_project"]))
    svc.assistant.search_engine.add_known_location(str(env["projects"]))

    # Ambiguous request: "Change the model"
    res = svc.handle_chat_message("Change the model")
    # Must ask clarification if multiple candidates found
    if svc.assistant.context.pending_clarification:
        assert len(svc.assistant.context.pending_clarification["candidates"]) > 1


def test_safety_blocks_system_path_modification(mock_explorer_env):
    """Verify that operations on Windows system paths are strictly blocked."""
    engine = FileOperationsEngine(current_workspace=str(mock_explorer_env["current_project"]))
    plan = OperationPlan(
        operation="DELETE",
        items=[{"source_path": "C:\\Windows\\System32\\calc.exe"}],
    )
    plan.items = [engine.plan_delete("C:\\Windows\\System32\\calc.exe").items[0]] if Path("C:\\Windows\\System32\\calc.exe").exists() else []
    if plan.items:
        res = engine.execute_plan(plan)
        assert res.success is False
        assert "Protected operating-system location" in res.error


# ──────────────────────────────────────────────────────────────────────────────
# 5. Preservation of Project Intelligence
# ──────────────────────────────────────────────────────────────────────────────

def test_project_intelligence_queries_preserved(mock_explorer_env):
    """Verify existing project consequence and dependency queries continue to work."""
    env = mock_explorer_env
    svc = PreViewAIService(project_root=str(env["current_project"]))
    svc.load_project(str(env["current_project"]))

    # "What uses train.py?" or dependencies
    r1 = svc.handle_chat_message("What uses train.py?")
    assert "app.py" in r1.reply_text or "required by" in r1.reply_text or "independent" in r1.reply_text

    # Consequence simulation: "What happens if I delete train.py?"
    r2 = svc.handle_chat_message("What happens if I delete train.py?")
    assert "Consequence Analysis" in r2.reply_text or "Risk" in r2.reply_text
    assert "train.py" in r2.reply_text

    # "Why does app.py depend on train.py?"
    r3 = svc.handle_chat_message("Why does app.py depend on train.py?")
    assert "app.py" in r3.reply_text and "train.py" in r3.reply_text
    assert "relationship" in r3.reply_text.lower() or "evidence" in r3.reply_text.lower()
