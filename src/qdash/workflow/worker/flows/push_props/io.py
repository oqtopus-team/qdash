from pathlib import Path

from qdash.workflow.worker.flows.push_props.formatter import represent_float, represent_none
from ruamel.yaml import YAML
from ruamel.yaml.comments import CommentedMap


def create_yaml_loader(style: str = "rt") -> YAML:
    """Create a YAML loader with specific configurations."""
    y = YAML(typ=style)
    y.preserve_quotes = True
    y.width = None
    y.indent(mapping=2, sequence=4, offset=2)
    if style != "rt":
        y.allow_unicode = True
        y.explicit_start = True
    return y


def add_custom_yaml_representers(yaml_obj: YAML) -> None:
    """Add custom representers for YAML serialization."""
    yaml_obj.representer.add_representer(type(None), represent_none)
    yaml_obj.representer.add_representer(float, represent_float)


class ChipPropertyYAMLHandler:
    """Handler for reading and writing chip properties in YAML format."""

    def __init__(self, base_path: str) -> None:
        """Initialize the YAML handler with a base path."""
        self.yaml = create_yaml_loader("rt")
        add_custom_yaml_representers(self.yaml)
        self.path = Path(base_path)

    def read(self) -> CommentedMap:
        with self.path.open("r") as f:
            return CommentedMap(self.yaml.load(f))

    def write(self, data: CommentedMap, output: str) -> None:
        with Path(output).open("w") as f:
            self.yaml.dump(data, f)
