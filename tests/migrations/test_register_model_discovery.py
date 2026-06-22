"""Tests for @register_model decorator and model discovery functionality."""

import logging
import os
import tempfile
import pytest

pytest.importorskip("sqlalchemy")

from src.database import _model_registry, metadata_obj, register_model, ChaCCBaseModel
from src.module_loader.discovery import discover_and_import_models


def test_register_model_adds_to_registry():
    """Verify that @register_model decorator adds the class to the registry."""
    @register_model
    class TestModel(ChaCCBaseModel):
        pass

    assert TestModel in _model_registry


def test_register_model_idempotent():
    """Verify that registering the same model twice doesn't duplicate."""
    from src.database import _model_registry as registry
    initial_count = len(registry)

    @register_model
    class UniqueTestModel(ChaCCBaseModel):
        pass

    register_model(UniqueTestModel)

    assert len(registry) == initial_count + 1


class TestModelDiscovery:
    """Tests for discover_and_import_models function."""

    def test_discover_and_import_adds_to_registry(self):
        """Verify that discovered modules with @register_model add to registry."""
        with tempfile.TemporaryDirectory() as tmpdir:
            model_file = os.path.join(tmpdir, "test_models.py")
            model_content = '''
from src.database import ChaCCBaseModel, register_model
from sqlalchemy import Column, String

@register_model
class DiscoveredModel(ChaCCBaseModel):
    __tablename__ = "discovered_models"
    name = Column(String(50))
'''
            with open(model_file, "w") as f:
                f.write(model_content)

            from src.database import _model_registry as registry
            initial_count = len(registry)

            discover_and_import_models(tmpdir, "discovered_test_module", logging.getLogger())

            assert len(registry) > initial_count

    def test_discover_and_import_adds_to_metadata(self):
        """Verify that discovered models have tables in metadata."""
        with tempfile.TemporaryDirectory() as tmpdir:
            model_file = os.path.join(tmpdir, "meta_models.py")
            model_content = '''
from src.database import ChaCCBaseModel, register_model
from sqlalchemy import Column, String, Integer

@register_model
class MetaTestModel(ChaCCBaseModel):
    __tablename__ = "meta_test_models"
    name = Column(String(50))
'''
            with open(model_file, "w") as f:
                f.write(model_content)

            discover_and_import_models(tmpdir, "meta_test_module", logging.getLogger())

            assert "meta_test_models" in metadata_obj.tables