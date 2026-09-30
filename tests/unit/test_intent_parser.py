"""
Unit tests for app/ai/intent_parser.py
"""
import pytest
from app.ai.intent_parser import RuleBasedIntentParser, IntentParser


def test_rename_simple():
    parser = RuleBasedIntentParser()
    action = parser.parse("rename dataset")
    assert action is not None
    assert action.operation == "RENAME"
    assert action.target == "dataset"
    assert action.destination == "dataset_renamed"


def test_rename_with_destination():
    parser = RuleBasedIntentParser()
    action = parser.parse("rename dataset to new_dataset")
    assert action is not None
    assert action.operation == "RENAME"
    assert action.target == "dataset"
    assert action.destination == "new_dataset"


def test_rename_as_destination():
    parser = RuleBasedIntentParser()
    action = parser.parse("rename dataset as data_backup")
    assert action is not None
    assert action.operation == "RENAME"
    assert action.target == "dataset"
    assert action.destination == "data_backup"


def test_rename_folder_prefix():
    parser = RuleBasedIntentParser()
    action = parser.parse("rename folder dataset")
    assert action is not None
    assert action.operation == "RENAME"
    assert action.target == "dataset"
    assert action.destination == "dataset_renamed"


def test_rename_quoted_with_spaces():
    parser = RuleBasedIntentParser()
    action = parser.parse("rename 'disease dataset' to 'disease dataset v2'")
    assert action is not None
    assert action.operation == "RENAME"
    assert action.target == "disease dataset"
    assert action.destination == "disease dataset v2"


def test_rename_with_file_extension():
    parser = RuleBasedIntentParser()
    action = parser.parse("rename model.pkl")
    assert action is not None
    assert action.operation == "RENAME"
    assert action.target == "model.pkl"
    assert action.destination == "model_renamed.pkl"


def test_natural_language_wrappers():
    parser = RuleBasedIntentParser()
    
    # "what happens if I rename dataset"
    a1 = parser.parse("what happens if I rename dataset?")
    assert a1 is not None
    assert a1.operation == "RENAME"
    assert a1.target == "dataset"

    # "simulate rename dataset"
    a2 = parser.parse("simulate rename dataset")
    assert a2 is not None
    assert a2.operation == "RENAME"
    assert a2.target == "dataset"

    # "can I delete dataset"
    a3 = parser.parse("can I delete dataset?")
    assert a3 is not None
    assert a3.operation == "DELETE"
    assert a3.target == "dataset"

    # "what if I move dataset to backup"
    a4 = parser.parse("what if I move dataset to backup")
    assert a4 is not None
    assert a4.operation == "MOVE"
    assert a4.target == "dataset"
    assert a4.destination == "backup"


def test_delete_variations():
    parser = RuleBasedIntentParser()
    assert parser.parse("delete dataset").target == "dataset"
    assert parser.parse("remove folder dataset/").target == "dataset"
    assert parser.parse("rmdir dataset").target == "dataset"
    assert parser.parse("clean up dataset").target == "dataset"


def test_move_variations():
    parser = RuleBasedIntentParser()
    m1 = parser.parse("move train.py to scripts/")
    assert m1.operation == "MOVE"
    assert m1.target == "train.py"
    assert m1.destination == "scripts/"

    m2 = parser.parse("move dataset")
    assert m2.operation == "MOVE"
    assert m2.target == "dataset"
    assert m2.destination == "archive/dataset"


def test_modify_variations():
    parser = RuleBasedIntentParser()
    mod = parser.parse("modify app.py")
    assert mod.operation == "MODIFY"
    assert mod.target == "app.py"


def test_create_variations():
    parser = RuleBasedIntentParser()
    c1 = parser.parse("create new_file.py")
    assert c1.operation == "CREATE"
    assert c1.target == "new_file.py"

    c2 = parser.parse("touch utils.py")
    assert c2.operation == "CREATE"
    assert c2.target == "utils.py"

    c3 = parser.parse("mkdir models")
    assert c3.operation == "CREATE"
    assert c3.target == "models"

    c4 = parser.parse("what happens if I create helper.py?")
    assert c4.operation == "CREATE"
    assert c4.target == "helper.py"

    c5 = parser.parse("new folder scripts")
    assert c5.operation == "CREATE"
    assert c5.target == "scripts"

