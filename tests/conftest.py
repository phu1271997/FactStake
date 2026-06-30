import sys
import pytest
from gltest.direct.loader import deploy_contract

@pytest.fixture
def direct_deploy(direct_vm):
    def _deploy(path, *args, **kwargs):
        # Reset the global contract registration state before each deployment in Direct Mode
        for mod_name in list(sys.modules.keys()):
            if mod_name.endswith('genvm_contracts'):
                mod = sys.modules[mod_name]
                if hasattr(mod, '__known_contract__'):
                    mod.__known_contract__ = None
        return deploy_contract(path, direct_vm, *args, **kwargs)
    return _deploy

@pytest.fixture
def creator(accounts):
    return accounts[0]

@pytest.fixture
def alice(accounts):
    return accounts[1]

@pytest.fixture
def bob(accounts):
    return accounts[2]
