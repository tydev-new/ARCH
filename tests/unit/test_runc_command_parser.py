import os
import sys
import pytest

# Add src to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

from src.runc_command_parser import RuncCommandParser

@pytest.fixture
def parser():
    return RuncCommandParser()

def test_parse_command_basic(parser):
    args = ['runc', 'create', '--bundle', '/path/to/bundle', 'container-id']
    subcommand, global_options, subcommand_options, container_id, namespace = parser.parse_command(args)
    
    assert subcommand == 'create'
    assert global_options == {}
    assert subcommand_options == ['--bundle', '/path/to/bundle']
    assert container_id == 'container-id'
    assert namespace == 'default'

def test_parse_command_complex(parser):
    args = ['runc', '--root', '/var/run/runc/k8s', '--log', '/var/log/runc.log',
            'checkpoint', '--image-path', '/path/to/checkpoint', 'container-id']
    subcommand, global_options, subcommand_options, container_id, namespace = parser.parse_command(args)
    
    assert subcommand == 'checkpoint'
    assert global_options == {
        'root': '/var/run/runc/k8s',
        'log': '/var/log/runc.log'
    }
    assert subcommand_options == ['--image-path', '/path/to/checkpoint']
    assert container_id == 'container-id'
    assert namespace == 'k8s'

def test_parse_command_empty(parser):
    with pytest.raises(ValueError, match="Empty command"):
        parser.parse_command([])

def test_parse_command_missing_components(parser):
    with pytest.raises(ValueError, match="Command must include at least a subcommand and container ID"):
        parser.parse_command(['runc'])

def test_parse_command_invalid_option_format(parser):
    with pytest.raises(ValueError, match="No subcommand found"):
        parser.parse_command(['runc', '-invalid', 'create', 'container-id'])

def test_should_intercept_create(parser):
    assert parser.should_intercept('create', {}) is True

def test_should_intercept_start(parser):
    assert parser.should_intercept('start', {}) is True

def test_should_intercept_checkpoint(parser):
    assert parser.should_intercept('checkpoint', {}) is True

def test_should_intercept_restore(parser):
    assert parser.should_intercept('restore', {}) is True

def test_should_intercept_delete(parser):
    assert parser.should_intercept('delete', {}) is True

def test_should_intercept_other(parser):
    assert parser.should_intercept('list', {}) is False 