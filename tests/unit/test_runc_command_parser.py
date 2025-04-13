import os
import sys
import pytest

# Add src to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

from src.runc_command_parser import RuncCommandParser

@pytest.fixture
def parser():
    """Create a RuncCommandParser instance for testing."""
    return RuncCommandParser()

def test_parse_command_basic(parser):
    args = ['runc', 'create', '--bundle', '/path/to/bundle', 'container-id']
    subcommand, global_options, subcommand_options, container_id, namespace = parser.parse_command(args)
    
    assert subcommand == 'create'
    assert global_options == {}
    assert subcommand_options == {'--bundle': '/path/to/bundle'}
    assert container_id == 'container-id'
    assert namespace == 'default'

def test_parse_command_complex(parser):
    args = ['runc', '--root', '/var/run/runc/k8s', '--log', '/var/log/runc.log',
            'checkpoint', '--image-path', '/path/to/checkpoint', 'container-id']
    subcommand, global_options, subcommand_options, container_id, namespace = parser.parse_command(args)
    
    assert subcommand == 'checkpoint'
    assert global_options == {
        '--root': '/var/run/runc/k8s',
        '--log': '/var/log/runc.log'
    }
    assert subcommand_options == {'--image-path': '/path/to/checkpoint'}
    assert container_id == 'container-id'
    assert namespace == 'k8s'

def test_parse_command_example1(parser):
    """Test parsing Example 1 from engineering requirements."""
    args = [
        'runc',
        '--root', '/run/containerd/runc/default',
        '--log', '/run/containerd/io.containerd.runtime.v2.task/default/tc/log.json',
        '--log-format', 'json',
        'create',
        '--bundle', '/run/containerd/io.containerd.runtime.v2.task/default/tc',
        '--pid-file', '/run/containerd/io.containerd.runtime.v2.task/default/tc/init.pid',
        'tc'
    ]
    
    subcommand, global_options, subcommand_options, container_id, namespace = parser.parse_command(args)
    
    assert subcommand == 'create'
    assert global_options == {
        '--root': '/run/containerd/runc/default',
        '--log': '/run/containerd/io.containerd.runtime.v2.task/default/tc/log.json',
        '--log-format': 'json'
    }
    assert subcommand_options == {
        '--bundle': '/run/containerd/io.containerd.runtime.v2.task/default/tc',
        '--pid-file': '/run/containerd/io.containerd.runtime.v2.task/default/tc/init.pid'
    }
    assert container_id == 'tc'
    assert namespace == 'default'

def test_parse_command_example2(parser):
    """Test parsing Example 2 from engineering requirements."""
    args = [
        'runc',
        '--root', '/run/containerd/runc/default',
        'start',
        'tc'
    ]
    
    subcommand, global_options, subcommand_options, container_id, namespace = parser.parse_command(args)
    
    assert subcommand == 'start'
    assert global_options == {'--root': '/run/containerd/runc/default'}
    assert subcommand_options == {}
    assert container_id == 'tc'
    assert namespace == 'default'

def test_parse_command_boolean_flags(parser):
    """Test parsing commands with boolean flags."""
    args = [
        'runc',
        '--root', '/run/containerd/runc/default',
        'checkpoint',
        '--file-locks',
        '--detach',
        'tc'
    ]
    
    subcommand, global_options, subcommand_options, container_id, namespace = parser.parse_command(args)
    
    assert subcommand == 'checkpoint'
    assert global_options == {'--root': '/run/containerd/runc/default'}
    assert subcommand_options == {'--file-locks': '', '--detach': ''}
    assert container_id == 'tc'
    assert namespace == 'default'

def test_parse_command_namespace_extraction(parser):
    """Test namespace extraction from --root path."""
    args = [
        'runc',
        '--root', '/run/containerd/runc/k8s',
        'start',
        'tc'
    ]
    
    subcommand, global_options, subcommand_options, container_id, namespace = parser.parse_command(args)
    assert namespace == 'k8s'

def test_parse_command_default_namespace(parser):
    """Test default namespace when no --root option."""
    args = ['runc', 'start', 'tc']
    
    subcommand, global_options, subcommand_options, container_id, namespace = parser.parse_command(args)
    assert namespace == 'default'

def test_parse_command_empty(parser):
    """Test empty command."""
    with pytest.raises(ValueError, match="Empty command"):
        parser.parse_command([])

def test_parse_command_missing_subcommand(parser):
    """Test command missing subcommand."""
    args = ['runc', '--root', '/path']
    with pytest.raises(ValueError, match="No subcommand found"):
        parser.parse_command(args)

def test_parse_command_missing_container_id(parser):
    """Test command missing container ID."""
    args = ['runc', '--root', '/path', 'start']
    subcommand, global_options, subcommand_options, container_id, namespace = parser.parse_command(args)
    
    assert subcommand == 'start'
    assert global_options == {'--root': '/path'}
    assert subcommand_options == {}
    assert container_id == ''
    assert namespace == 'path'

def test_should_intercept_create(parser):
    assert parser.should_intercept('create', {}) is True

def test_should_intercept_start(parser):
    assert parser.should_intercept('start', {}) is True

def test_should_intercept_checkpoint(parser):
    assert parser.should_intercept('checkpoint', {}) is True

def test_should_intercept_restore(parser):
    assert parser.should_intercept('restore', {}) is False

def test_should_intercept_delete(parser):
    assert parser.should_intercept('delete', {}) is True

def test_should_intercept_other(parser):
    assert parser.should_intercept('list', {}) is False 