"""Portable single-scene specifications compiled with the Python MVS builder.

The compact scene format follows pdbe-chat's builder actions. Construction is
independent of LangChain, HTTP, artifact storage, and the viewer lifecycle.
"""

import json
import math
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Annotated, Any, Literal, Union, get_args
from urllib.parse import urlsplit

from molviewspec.builder import create_builder
from molviewspec.nodes import ColorNamesT, SchemaT
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    JsonValue,
    StringConstraints,
    ValidationError,
    field_validator,
    model_validator,
)


class Spec(BaseModel):
    model_config = ConfigDict(
        extra="forbid", allow_inf_nan=False, populate_by_name=True
    )


Text = Annotated[str, StringConstraints(min_length=1, max_length=2000)]
Vec3 = tuple[float, float, float]
Positive = Annotated[float, Field(gt=0)]
Ref = Annotated[str, StringConstraints(pattern=r"^[A-Za-z0-9_-]{1,64}$")]


class MolQL(Spec):
    """Serialized base-language query; never executable Python/JavaScript."""

    molql: dict[str, JsonValue]

    @field_validator("molql")
    @classmethod
    def query(cls, value):
        symbols = json.loads(
            (
                Path(__file__).parent
                / "skills/molview-spec/references/molql-symbols.json"
            ).read_text()
        )
        count = 0

        def visit(expr, depth=0):
            nonlocal count
            count += 1
            if depth > 32 or count > 2000:
                raise ValueError("MolQL query exceeds depth/node limits")
            if isinstance(expr, (str, bool, int, float)):
                if isinstance(expr, float) and not math.isfinite(expr):
                    raise ValueError("MolQL literals must be finite")
                return
            if not isinstance(expr, dict):
                raise ValueError("Invalid MolQL expression")
            if (
                set(expr) == {"name"}
                and isinstance(expr["name"], str)
                and expr["name"] in symbols
            ):
                return
            if not {"head"} <= set(expr) <= {"head", "args"}:
                raise ValueError("MolQL requires a symbol or application")
            head = expr["head"]
            if (
                not isinstance(head, dict)
                or set(head) != {"name"}
                or not isinstance(head["name"], str)
                or head["name"] not in symbols
            ):
                raise ValueError("Unknown MolQL application symbol")
            args = expr.get("args", [])
            if not isinstance(args, (dict, list)):
                raise ValueError("MolQL args must be an object or array")
            info = symbols[head["name"]]
            keys = (
                set(args)
                if isinstance(args, dict)
                else {str(i) for i in range(len(args))}
            )
            if info["args"] is not None and not keys <= set(info["args"]):
                raise ValueError("Unknown MolQL argument")
            if not set(info["required"]) <= keys:
                raise ValueError("Missing required MolQL argument")
            for arg in args.values() if isinstance(args, dict) else args:
                visit(arg, depth + 1)

        if "head" not in value:
            raise ValueError("MolQL selector must be an application")
        visit(value)
        if not symbols[value["head"]["name"]]["query"]:
            raise ValueError("MolQL selector must return an element selection query")
        return value


def valid_color(value: str) -> str:
    value = value.strip().lower()
    if value not in get_args(ColorNamesT) and not re.fullmatch(r"#[0-9a-f]{6}", value):
        raise ValueError("Use a named CSS color or #RRGGBB")
    return value


def _aliases(value: Any, mapping: dict[str, tuple[str, ...]]) -> Any:
    """Accept known historical spellings without discarding conflicting inputs."""
    if not isinstance(value, dict):
        return value
    result = dict(value)
    for canonical, aliases in mapping.items():
        for alias in aliases:
            if alias not in result:
                continue
            other = result.pop(alias)
            if canonical in result and result[canonical] != other:
                raise ValueError(f"Conflicting {canonical} and {alias} values")
            result[canonical] = other
    return result


def _scene_input(value: Any) -> Any:
    value = _aliases(
        value,
        {"pdb_id": ("pdbId", "entry_id", "entryId"), "include_water": ("show_water",)},
    )
    if not isinstance(value, dict):
        return value
    result = dict(value)
    structure = result.get("structure")
    if isinstance(structure, dict):
        structure = _aliases(
            structure,
            {
                "pdb_id": ("pdbId", "entry_id", "entryId"),
                "include_water": ("show_water",),
                "url": ("uri",),
            },
        )
        for key in ("pdb_id", "include_water"):
            if key in structure:
                item = structure.pop(key)
                if key in result and result[key] != item:
                    raise ValueError(f"Conflicting scene and structure {key}")
                result[key] = item
        result["structure"] = structure
        if "pdb_id" not in result and isinstance(structure.get("url"), str):
            match = re.search(
                r"/((?:[1-9][a-z0-9]{3}|pdb_[a-z0-9]{8}))\.(?:bcif|cif|mmcif|pdb)$",
                urlsplit(structure["url"]).path,
                re.I,
            )
            if match:
                result["pdb_id"] = match.group(1)
    if "component" in result:
        component = result.pop("component")
        if result.get("components"):
            raise ValueError("Use components or component, not both")
        result["components"] = [component]
    if result.get("components") == []:
        result.pop("components")
    if result.get("primitives") == []:
        result.pop("primitives")
    if result.get("description") == "":
        result["description"] = None
    return result


def _static_selector(value: Any) -> Any:
    return value.strip().lower() if isinstance(value, str) else value


class Expression(Spec):
    """Explicit mmCIF identifiers; author and label numbering remain distinct."""

    label_entity_id: str | None = None
    label_asym_id: str | None = None
    auth_asym_id: str | None = None
    label_comp_id: str | None = None
    auth_comp_id: str | None = None
    pdbx_PDB_ins_code: str | None = None
    label_atom_id: str | None = None
    auth_atom_id: str | None = None
    type_symbol: str | None = None
    # Stable Mol* instance identifier for assembly/crystal copies.
    instance_id: str | None = None
    label_seq_id: int | None = None
    auth_seq_id: int | None = None
    beg_label_seq_id: int | None = None
    end_label_seq_id: int | None = None
    beg_auth_seq_id: int | None = None
    end_auth_seq_id: int | None = None
    residue_index: int | None = None
    atom_id: int | None = None
    atom_index: int | None = None

    @field_validator("*", mode="before")
    @classmethod
    def no_boolean_ids(cls, value):
        if isinstance(value, bool):
            raise ValueError("Identifiers must be strings or integers, not booleans")
        return value

    @model_validator(mode="after")
    def check_ranges(self):
        if not self.model_dump(exclude_none=True):
            raise ValueError(
                "A selector expression must contain at least one identifier"
            )
        for kind in ("label", "auth"):
            start, end = (
                getattr(self, f"beg_{kind}_seq_id"),
                getattr(self, f"end_{kind}_seq_id"),
            )
            if start is not None and end is not None and start > end:
                raise ValueError("Selector range start must not exceed its end")
        return self


Selector = Union[
    Literal[
        "all",
        "polymer",
        "protein",
        "nucleic",
        "branched",
        "ligand",
        "ion",
        "water",
        "coarse",
    ],
    Expression,
    MolQL,
    Annotated[list[Expression], Field(min_length=1, max_length=500)],
]


class Focus(Spec):
    direction: Vec3 | None = None
    up: Vec3 | None = None
    radius: float | None = Field(default=None, gt=0)
    radius_factor: float | None = Field(default=None, gt=0)
    radius_extent: float | None = Field(default=None, ge=0)


class Camera(Spec):
    target: Vec3
    position: Vec3
    up: Vec3 = (0, 1, 0)

    @model_validator(mode="after")
    def check_orientation(self):
        direction = tuple(p - t for p, t in zip(self.position, self.target))
        cross = tuple(
            direction[(i + 1) % 3] * self.up[(i + 2) % 3]
            - direction[(i + 2) % 3] * self.up[(i + 1) % 3]
            for i in range(3)
        )
        if not any(cross):
            raise ValueError(
                "Camera position, target and up must define a valid orientation"
            )
        return self


class Canvas(Spec):
    background_color: str = "white"
    _color = field_validator("background_color")(valid_color)


class Transform(Spec):
    rotation: Annotated[list[float], Field(min_length=9, max_length=9)] | None = None
    translation: Vec3 | None = None
    rotation_center: Vec3 | Literal["centroid"] | None = None
    matrix: Annotated[list[float], Field(min_length=16, max_length=16)] | None = None

    @model_validator(mode="after")
    def geometry(self):
        if self.matrix is not None and any(
            v is not None
            for v in (self.rotation, self.translation, self.rotation_center)
        ):
            raise ValueError("Use matrix or rotation/translation/rotation_center")
        if not self.model_dump(exclude_none=True):
            raise ValueError("Provide a transform matrix, rotation or translation")
        if self.matrix is not None and any(
            abs(self.matrix[i] - expected) > 1e-6
            for i, expected in ((3, 0), (7, 0), (11, 0), (15, 1))
        ):
            raise ValueError("Matrix must be an affine column-major transform")
        if self.rotation is not None:
            # Match the builder's requirement for a proper rotation matrix.
            r = self.rotation
            for i in range(3):
                for j in range(3):
                    dot = sum(r[3 * i + k] * r[3 * j + k] for k in range(3))
                    if abs(dot - (1 if i == j else 0)) > 1e-5:
                        raise ValueError("rotation must be orthonormal")
            determinant = (
                r[0] * (r[4] * r[8] - r[5] * r[7])
                - r[3] * (r[1] * r[8] - r[2] * r[7])
                + r[6] * (r[1] * r[5] - r[2] * r[4])
            )
            if abs(determinant - 1) > 1e-5:
                raise ValueError("rotation must have determinant 1")
        return self


class PositionExpressions(Spec):
    structure_ref: Ref | None = None
    expressions: list[Expression] = Field(min_length=1, max_length=500)


class QueryPosition(MolQL):
    structure_ref: Ref | None = None


Position = Union[Vec3, Expression, PositionExpressions, QueryPosition]


class PrimitiveStyle(Spec):
    color: str | None = None
    tooltip: Text | None = None
    _color = field_validator("color")(
        lambda value: valid_color(value) if value is not None else value
    )


class Sphere(PrimitiveStyle):
    type: Literal["sphere"]
    center: Position
    radius: Positive = 1


class Tube(PrimitiveStyle):
    type: Literal["tube"]
    start: Position
    end: Position
    radius: Positive = 0.05
    dash_length: Positive | None = None


class Arrow(PrimitiveStyle):
    type: Literal["arrow"]
    start: Position
    end: Position | None = None
    direction: Vec3 | None = None
    length: Positive | None = None
    show_start_cap: bool = False
    show_end_cap: bool = True
    show_tube: bool = True
    tube_radius: Positive = 0.05
    tube_dash_length: Positive | None = None
    start_cap_length: Positive | None = None
    start_cap_radius: Positive | None = None
    end_cap_length: Positive | None = None
    end_cap_radius: Positive | None = None

    @model_validator(mode="after")
    def endpoint(self):
        if (self.end is None) == (self.direction is None):
            raise ValueError("Arrow needs exactly one of end or direction")
        if self.direction is not None and not any(self.direction):
            raise ValueError("Arrow direction must be nonzero")
        return self


class Distance(PrimitiveStyle):
    type: Literal["distance"]
    start: Position
    end: Position
    radius: Positive = 0.05
    dash_length: Positive | None = None
    label_template: Text = "{{distance}}"
    label_size: Positive | None = None
    label_color: str | None = None
    _label_color = field_validator("label_color")(
        lambda value: valid_color(value) if value is not None else value
    )


class Angle(PrimitiveStyle):
    type: Literal["angle"]
    a: Position
    b: Position
    c: Position
    label_template: Text = "{{angle}}"
    label_size: Positive | None = None
    label_color: str | None = None
    show_vector: bool = True
    show_section: bool = True
    _label_color = field_validator("label_color")(
        lambda value: valid_color(value) if value is not None else value
    )


class PrimitiveLabel(Spec):
    type: Literal["label"]
    position: Position
    text: Text
    label_size: Positive = 1
    label_color: str | None = None
    label_offset: float = 0
    _label_color = field_validator("label_color")(
        lambda value: valid_color(value) if value is not None else value
    )


class Ellipse(PrimitiveStyle):
    type: Literal["ellipse"]
    center: Position
    major_axis: Vec3
    minor_axis: Vec3
    radius_major: Positive | None = None
    radius_minor: Positive | None = None
    as_circle: bool = False
    theta_start: float | None = None
    theta_end: float | None = None

    @model_validator(mode="after")
    def axes(self):
        cross = [
            self.major_axis[(i + 1) % 3] * self.minor_axis[(i + 2) % 3]
            - self.major_axis[(i + 2) % 3] * self.minor_axis[(i + 1) % 3]
            for i in range(3)
        ]
        if not any(cross):
            raise ValueError("Primitive axes must be nonzero and nonparallel")
        return self


class Ellipsoid(PrimitiveStyle):
    type: Literal["ellipsoid"]
    center: Position
    radius: Positive | tuple[Positive, Positive, Positive]
    major_axis: Vec3 = (1, 0, 0)
    minor_axis: Vec3 = (0, 1, 0)

    @model_validator(mode="after")
    def axes(self):
        cross = [
            self.major_axis[(i + 1) % 3] * self.minor_axis[(i + 2) % 3]
            - self.major_axis[(i + 2) % 3] * self.minor_axis[(i + 1) % 3]
            for i in range(3)
        ]
        if not any(cross):
            raise ValueError("Primitive axes must be nonzero and nonparallel")
        return self


class Box(Spec):
    type: Literal["box"]
    center: Position
    extent: tuple[Positive, Positive, Positive]
    show_faces: bool = True
    face_color: str | None = None
    show_edges: bool = False
    edge_radius: Positive = 0.1
    edge_color: str | None = None
    show_wireframe: bool = False
    wireframe_color: str | None = None
    wireframe_width: Positive | None = None
    tooltip: Text | None = None
    _colors = field_validator("face_color", "edge_color", "wireframe_color")(
        lambda value: valid_color(value) if value is not None else value
    )


class Mesh(PrimitiveStyle):
    type: Literal["mesh"]
    vertices: list[float] = Field(min_length=9, max_length=30000)
    indices: list[Annotated[int, Field(ge=0, strict=True)]] = Field(
        min_length=3, max_length=30000
    )
    show_triangles: bool = True
    show_wireframe: bool = False
    wireframe_width: Positive | None = None
    wireframe_color: str | None = None
    _wireframe_color = field_validator("wireframe_color")(
        lambda value: valid_color(value) if value is not None else value
    )

    @model_validator(mode="after")
    def geometry(self):
        stride = 2 if self.type == "lines" else 3
        if len(self.vertices) % 3 or len(self.indices) % stride:
            raise ValueError(
                "Vertices/indices must form complete points and faces/lines"
            )
        if max(self.indices) >= len(self.vertices) // 3:
            raise ValueError("Primitive index is outside the vertices array")
        return self


class Lines(PrimitiveStyle):
    type: Literal["lines"]
    vertices: list[float] = Field(min_length=6, max_length=30000)
    indices: list[Annotated[int, Field(ge=0, strict=True)]] = Field(
        min_length=2, max_length=30000
    )
    width: Positive = 1

    @model_validator(mode="after")
    def geometry(self):
        if len(self.vertices) % 3 or len(self.indices) % 2:
            raise ValueError("Vertices/indices must form complete points and lines")
        if max(self.indices) >= len(self.vertices) // 3:
            raise ValueError("Primitive index is outside the vertices array")
        return self


Primitive = Annotated[
    Union[
        Sphere,
        Tube,
        Arrow,
        Distance,
        Angle,
        PrimitiveLabel,
        Ellipse,
        Ellipsoid,
        Box,
        Mesh,
        Lines,
    ],
    Field(discriminator="type"),
]


class Clip(Spec):
    type: Literal["plane", "sphere", "box"]
    point: Vec3 | None = None
    normal: Vec3 | None = None
    center: Vec3 | None = None
    radius: float | None = Field(default=None, gt=0)
    size: Vec3 | None = None
    invert: bool = False
    variant: Literal["object", "pixel"] = "pixel"

    @model_validator(mode="after")
    def geometry(self):
        fields = {
            "plane": {"point", "normal"},
            "sphere": {"center", "radius"},
            "box": {"center", "size"},
        }[self.type]
        supplied = self.model_fields_set - {"type", "invert", "variant"}
        if supplied != fields or any(getattr(self, key) is None for key in fields):
            raise ValueError(f"{self.type} clipping requires exactly {sorted(fields)}")
        if self.normal is not None and not any(self.normal):
            raise ValueError("Clipping plane normal must be nonzero")
        if self.size is not None and any(value <= 0 for value in self.size):
            raise ValueError("Clipping box dimensions must be positive")
        return self


class Representation(Spec):
    type: Literal[
        "cartoon",
        "ball_and_stick",
        "surface",
        "spacefill",
        "carbohydrate",
        "backbone",
        "line",
        "putty",
    ] = "cartoon"
    opacity: float | None = Field(
        default=None,
        ge=0,
        le=1,
        description="Representation opacity: 0 is transparent and 1 is opaque. Set components[].representation.opacity (or annotations[].representation.opacity), not component-level opacity.",
    )
    size_factor: float | None = Field(default=None, gt=0)
    ignore_hydrogens: bool | None = None
    size_theme: Literal["uniform", "uncertainty"] | None = None
    surface_type: Literal["molecular", "gaussian"] | None = None
    tubular_helices: bool | None = None
    clip: Clip | Annotated[list[Clip], Field(min_length=1, max_length=20)] | None = None

    @field_validator("type", mode="before")
    @classmethod
    def aliases(cls, value):
        value = value.strip().lower() if isinstance(value, str) else value
        return {
            "sticks": "ball_and_stick",
            "stick": "ball_and_stick",
            "ball-and-stick": "ball_and_stick",
            "ribbon": "cartoon",
            "lines": "line",
            "space_fill": "spacefill",
            "space-fill": "spacefill",
            "space-filling": "spacefill",
        }.get(value, value)

    @model_validator(mode="after")
    def options(self):
        for key, allowed in {
            "size_theme": {"putty"},
            "surface_type": {"surface"},
            "tubular_helices": {"cartoon"},
            "ignore_hydrogens": {"ball_and_stick", "line", "spacefill", "surface"},
        }.items():
            if getattr(self, key) is not None and self.type not in allowed:
                raise ValueError(f"{key} does not apply to {self.type}")
        return self


class Isosurface(Spec):
    relative_isovalue: float | None = None
    absolute_isovalue: float | None = None
    show_faces: bool = True
    show_wireframe: bool = False

    @model_validator(mode="after")
    def isovalue(self):
        if self.relative_isovalue is not None and self.absolute_isovalue is not None:
            raise ValueError("Set only one relative or absolute isovalue")
        if self.relative_isovalue is None and self.absolute_isovalue is None:
            self.relative_isovalue = 1.0
        return self


class Volume(Spec):
    url: str
    format: Literal["map", "bcif", "mmcif", "dx", "dxbin"] = "map"
    channel_id: Text | None = None
    representation: Isosurface = Field(default_factory=Isosurface)
    color: str | None = None
    opacity: float | None = Field(default=None, ge=0, le=1)

    @field_validator("url")
    @classmethod
    def density_url(cls, value):
        parts = urlsplit(value)
        host = parts.hostname or ""
        if (
            parts.scheme != "https"
            or parts.username
            or parts.password
            or parts.port not in (None, 443)
            or parts.fragment
            or not any(
                host == domain or host.endswith("." + domain)
                for domain in ("ebi.ac.uk", "wwpdb.org")
            )
        ):
            raise ValueError("Density URLs must use HTTPS on ebi.ac.uk or wwpdb.org")
        return value

    @field_validator("color")
    @classmethod
    def density_color(cls, value):
        return valid_color(value) if value is not None else value


class AnnotationData(Spec):
    """Annotation table in an allowed HTTPS resource or the coordinate CIF."""

    schema_: SchemaT = Field(alias="schema")
    uri: str | None = None
    format: Literal["cif", "bcif", "json"] | None = None
    block_header: Text | None = None
    block_index: int | None = Field(default=None, ge=0, strict=True)
    category_name: Text | None = None
    field_name: Text | None = None
    field_remapping: dict[str, str | None] | None = None

    @model_validator(mode="after")
    def source(self):
        if self.uri is not None:
            Volume.density_url(self.uri)
            if self.format is None:
                raise ValueError("External annotation data requires format")
        elif self.format is not None or self.category_name is None:
            raise ValueError("Source annotations require category_name and no format")
        return self


class ComponentData(AnnotationData):
    field_values: list[Text] | None = Field(default=None, max_length=500)


class Color(Spec):
    @model_validator(mode="before")
    @classmethod
    def normalize(cls, value):
        return _aliases(value, {"color": ("value",)})

    _selector_case = field_validator("selector", mode="before")(_static_selector)
    color: str
    selector: Selector | None = None
    _color = field_validator("color")(valid_color)


class Label(Spec):
    text: Text
    scene: bool = False


class Tooltip(Spec):
    text: Text


class ComponentStyle(Spec):
    @model_validator(mode="before")
    @classmethod
    def normalize_opacity(cls, value):
        """Recover the common misplaced field without guessing conflicting intent."""
        if not isinstance(value, dict) or "opacity" not in value:
            return value
        result = dict(value)
        opacity = result.pop("opacity")
        representation = result.get("representation", {})
        if isinstance(representation, str):
            representation = {"type": representation}
        elif isinstance(representation, dict):
            representation = dict(representation)
        else:
            raise ValueError(
                "To set opacity, use representation: {type: ..., opacity: ...}; representation must be an object or a supported representation name"
            )
        if "opacity" in representation and representation["opacity"] != opacity:
            raise ValidationError.from_exception_data(
                "Component opacity",
                [
                    {
                        "type": "value_error",
                        "loc": ("representation", "opacity"),
                        "input": None,
                        "ctx": {
                            "error": ValueError(
                                "Conflicting component opacity and representation.opacity; remove component-level opacity and provide one representation.opacity value"
                            )
                        },
                    }
                ],
            )
        representation["opacity"] = opacity
        result["representation"] = representation
        return result

    _selector_case = field_validator("selector", mode="before", check_fields=False)(
        _static_selector
    )

    representation: Representation = Field(
        default_factory=Representation,
        description="Visual style; use an object with type and opacity for transparency, e.g. {type: 'cartoon', opacity: 0.3}. Opacity belongs inside representation, not on the component or annotation.",
    )
    color: Color | None = None
    colors: list[Color] = Field(default_factory=list, max_length=100)
    color_from: list[AnnotationData] = Field(default_factory=list, max_length=20)
    label: Label | None = None
    tooltip: Tooltip | None = None
    focus: bool | Focus = False

    @field_validator(
        "representation", mode="before", json_schema_input_type=Representation | str
    )
    @classmethod
    def representation_shorthand(cls, value):
        return {"type": value} if isinstance(value, str) else value

    @field_validator("color", mode="before", json_schema_input_type=Color | str | None)
    @classmethod
    def color_shorthand(cls, value):
        return {"color": value} if isinstance(value, str) else value

    @field_validator("label", mode="before", json_schema_input_type=Label | str | None)
    @classmethod
    def text_shorthand(cls, value):
        return {"text": value} if isinstance(value, str) else value

    @field_validator(
        "tooltip", mode="before", json_schema_input_type=Tooltip | str | None
    )
    @classmethod
    def tooltip_shorthand(cls, value):
        return {"text": value} if isinstance(value, str) else value


class Component(ComponentStyle):
    selector: Selector = "polymer"
    annotation: ComponentData | None = None

    @model_validator(mode="after")
    def selection_source(self):
        if self.annotation is not None and "selector" in self.model_fields_set:
            raise ValueError("Use selector or annotation for a component, not both")
        return self


class Annotation(ComponentStyle):
    selector: Selector
    group_id: Text | None = None


class Structure(Spec):
    source: Literal["pdbe_bcif"] = "pdbe_bcif"
    type: Literal["model", "assembly", "symmetry", "symmetry_mates"] = "model"
    format: Literal[
        "bcif", "mmcif", "pdb", "pdbqt", "gro", "xyz", "mol", "sdf", "mol2", "lammpstrj"
    ] = "bcif"
    url: str | None = None
    assembly_id: Text | None = None
    model_index: int = Field(default=0, ge=0, strict=True)
    block_index: int | None = Field(default=None, ge=0, strict=True)
    block_header: Text | None = None
    ref: Ref | None = None
    transform: Transform | None = None
    instances: list[Transform] = Field(default_factory=list, max_length=100)
    ijk_min: tuple[int, int, int] = (-1, -1, -1)
    ijk_max: tuple[int, int, int] = (1, 1, 1)
    radius: float = Field(default=5, gt=0, le=50)

    @model_validator(mode="before")
    @classmethod
    def normalize(cls, value):
        value = _aliases(value, {"url": ("uri",)})
        if isinstance(value, dict):
            value = dict(value)
            if isinstance(value.get("type"), str):
                kind = value["type"].strip().lower().replace("-", "_")
                value["type"] = "symmetry_mates" if kind == "symmetrymates" else kind
            if isinstance(value.get("format"), str):
                value["format"] = value["format"].strip().lower()
            if isinstance(value.get("assembly_id"), int) and not isinstance(
                value["assembly_id"], bool
            ):
                value["assembly_id"] = str(value["assembly_id"])
        return value

    @field_validator("url")
    @classmethod
    def coordinate_url(cls, value):
        if value is not None:
            parts = urlsplit(value)
            if (
                parts.scheme != "https"
                or parts.netloc != "www.ebi.ac.uk"
                or parts.fragment
            ):
                raise ValueError(
                    "Coordinate URLs must use https://www.ebi.ac.uk (the App's allowed origin)"
                )
        return value

    @model_validator(mode="after")
    def structure_options(self):
        allowed = {
            "type",
            "source",
            "format",
            "url",
            "model_index",
            "block_index",
            "block_header",
            "ref",
            "transform",
            "instances",
        }
        allowed.update(
            {
                "assembly": {"assembly_id"},
                "symmetry": {"ijk_min", "ijk_max"},
                "symmetry_mates": {"radius"},
            }.get(self.type, set())
        )
        if self.model_fields_set - allowed:
            raise ValueError(
                "Structure options do not match the selected structure type"
            )
        if any(lo > hi for lo, hi in zip(self.ijk_min, self.ijk_max)):
            raise ValueError("ijk_min must not exceed ijk_max")
        if self.type == "symmetry" and any(
            hi - lo > 4 for lo, hi in zip(self.ijk_min, self.ijk_max)
        ):
            raise ValueError(
                "Symmetry scenes support at most five cells along each axis"
            )
        return self


class StructureLayer(Spec):
    @model_validator(mode="before")
    @classmethod
    def normalize(cls, value):
        return _scene_input(value)

    pdb_id: str = Field(pattern=r"^(?:[1-9][a-z0-9]{3}|pdb_[a-z0-9]{8})$")
    structure: Structure = Field(default_factory=Structure)
    include_water: bool = False
    components: list[Component] = Field(
        default_factory=lambda: [Component(color=Color(color="#91bfdb"))],
        min_length=1,
        max_length=100,
    )
    annotations: list[Annotation] = Field(default_factory=list, max_length=500)
    labels_from: list[AnnotationData] = Field(default_factory=list, max_length=20)
    tooltips_from: list[AnnotationData] = Field(default_factory=list, max_length=20)
    primitives: list[Primitive] = Field(default_factory=list, max_length=100)
    focus: bool | Focus = False
    sources: list[str] = Field(
        default_factory=list,
        max_length=50,
        description="Evidence URLs used to select or describe features; supplied by the caller.",
    )

    @field_validator("pdb_id", mode="before")
    @classmethod
    def lowercase_id(cls, value):
        return value.strip().lower() if isinstance(value, str) else value

    @field_validator("annotations")
    @classmethod
    def annotation_groups(cls, values):
        labels = {}
        errors = []
        for index, item in enumerate(values):
            if item.group_id is None:
                continue
            problems = []
            if item.label is None:
                problems.append(
                    (
                        "label",
                        "Provide a label for each grouped annotation, or remove group_id for coloring/tooltips without a shared label",
                    )
                )
            else:
                text = labels.setdefault(item.group_id, item.label.text)
                if item.label.text != text:
                    problems.append(
                        (
                            "label",
                            "Annotations in the same group_id must use matching label text",
                        )
                    )
            if isinstance(item.selector, (str, MolQL)):
                problems.append(
                    (
                        "selector",
                        "Grouped annotations require expression selectors, not named selections; remove group_id to use a named selection",
                    )
                )
            for field, message in problems:
                errors.append(
                    {
                        "type": "value_error",
                        "loc": (index, field),
                        "ctx": {"error": ValueError(message)},
                    }
                )
        if errors:
            raise ValidationError.from_exception_data("Annotation groups", errors)
        return values

    @field_validator("sources")
    @classmethod
    def evidence_urls(cls, values):
        for value in values:
            if urlsplit(value).scheme != "https" or not urlsplit(value).hostname:
                raise ValueError("Evidence sources must be HTTPS URLs")
        return values


class Scene(StructureLayer):
    title: Text | None = None
    description: Text | None = None
    description_format: Literal["plaintext", "markdown"] = "plaintext"
    volumes: list[Volume] = Field(default_factory=list, max_length=20)
    canvas: Canvas = Field(default_factory=Canvas)
    camera: Camera | None = None
    additional_structures: list[StructureLayer] = Field(
        default_factory=list, max_length=9
    )

    @model_validator(mode="after")
    def references(self):
        layers = [self, *self.additional_structures]
        refs = [
            layer.structure.ref for layer in layers if layer.structure.ref is not None
        ]
        if len(refs) != len(set(refs)):
            raise ValueError("Structure references must be unique within a scene")
        for layer in layers:
            for primitive in layer.primitives:
                for name in ("center", "start", "end", "a", "b", "c", "position"):
                    position = getattr(primitive, name, None)
                    ref = getattr(position, "structure_ref", None)
                    if ref is not None and ref not in refs:
                        raise ValueError(f"Unknown primitive structure_ref: {ref}")
        return self


class BuildMvsInput(Spec):
    version: Literal[1] = 1
    builder: Scene


class Transition(Spec):
    duration_ms: int = Field(default=1500, ge=0, le=30000, strict=True)
    trajectory: Literal["linear", "linear-relative", "leap", "leap-relative"] = "linear"
    easing: Literal[
        "linear",
        "bounce-in",
        "bounce-out",
        "bounce-in-out",
        "circle-in",
        "circle-out",
        "circle-in-out",
        "cubic-in",
        "cubic-out",
        "cubic-in-out",
        "exp-in",
        "exp-out",
        "exp-in-out",
        "quad-in",
        "quad-out",
        "quad-in-out",
        "sin-in",
        "sin-out",
        "sin-in-out",
    ] = "linear"


class StoryScene(Spec):
    @model_validator(mode="before")
    @classmethod
    def normalize(cls, value):
        value = _aliases(value, {"duration_ms": ("linger_duration_ms",)})
        if isinstance(value, dict) and value.get("description") == "":
            value["description"] = None
        return value

    id: str = Field(pattern=r"^[A-Za-z0-9_-]{1,64}$")
    title: Text
    description: Text | None = None
    duration_ms: int = Field(default=6500, ge=0, le=300000, strict=True)
    transition_duration_ms: int = Field(default=1500, ge=0, le=30000, strict=True)
    transition: Transition | None = None
    description_format: Literal["plaintext", "markdown"] = "plaintext"
    builder: Scene


class Story(Spec):
    @model_validator(mode="before")
    @classmethod
    def normalize(cls, value):
        if not isinstance(value, dict):
            return value
        value = dict(value)
        if value.get("description") == "":
            value["description"] = None
        if isinstance(value.get("scenes"), list):
            value["scenes"] = [
                {"id": f"scene-{index + 1}", "title": f"Scene {index + 1}", **item}
                if isinstance(item, dict)
                else item
                for index, item in enumerate(value["scenes"])
            ]
        return value

    title: Text
    description: Text | None = None
    description_format: Literal["plaintext", "markdown"] = "plaintext"
    scenes: list[StoryScene] = Field(min_length=2, max_length=20)

    @model_validator(mode="after")
    def unique_ids(self):
        ids = [scene.id for scene in self.scenes]
        if len(ids) != len(set(ids)):
            raise ValueError("Story scene IDs must be unique")
        return self


class BuildStoryInput(Spec):
    version: Literal[1] = 1
    story: Story


def build_mvs_story(arguments: dict[str, Any]) -> dict[str, Any]:
    """Compose validated single scenes into one native multiple-state MVSJ."""
    story = BuildStoryInput.model_validate(arguments).story
    snapshots = []
    scenes = []
    sources: list[str] = []
    warnings: list[str] = []
    for item in story.scenes:
        spec = _normalized_layer(item.builder)
        spec["additional_structures"] = [
            _normalized_layer(layer) for layer in item.builder.additional_structures
        ]
        spec["title"] = item.title
        if item.description:
            spec["description"] = item.description
        compiled = build_mvs({"builder": spec})
        metadata = {
            "key": item.id,
            "title": item.title,
            "duration_ms": item.duration_ms,
            "transition_duration_ms": item.transition_duration_ms,
            "description_format": item.description_format,
        }
        if item.description:
            metadata["description"] = item.description
        if item.transition is not None:
            # Released Python 1.8 predates this Mol* 5.13.1 root node.
            compiled["mvsj"]["root"].setdefault("children", []).append(
                {"kind": "transition", "params": item.transition.model_dump()}
            )
            if "transition_duration_ms" not in item.model_fields_set:
                metadata["transition_duration_ms"] = item.transition.duration_ms
        snapshots.append({"root": compiled["mvsj"]["root"], "metadata": metadata})
        scenes.append(
            {
                **item.model_dump(mode="json", by_alias=True, exclude_none=True),
                "transition_duration_ms": metadata["transition_duration_ms"],
                "builder": compiled["builder"],
                "legend": compiled["legend"],
                "coordinate_url": compiled["coordinate_url"],
            }
        )
        sources.extend(compiled["sources"])
        warnings.extend(compiled["warnings"])
    normalized = story.model_dump(mode="json", by_alias=True, exclude_none=True)
    normalized["scenes"] = [
        {k: v for k, v in scene.items() if k not in {"legend", "coordinate_url"}}
        for scene in scenes
    ]
    metadata = {
        "title": story.title,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "version": "1.8",
        "description_format": story.description_format,
    }
    if story.description:
        metadata["description"] = story.description
    return {
        "version": 1,
        "story": normalized,
        "scenes": scenes,
        "mvsj": {"kind": "multiple", "metadata": metadata, "snapshots": snapshots},
        "warnings": list(dict.fromkeys(warnings)),
        "sources": list(dict.fromkeys(sources)),
    }


def _selector(value: Any) -> Any:
    if isinstance(value, (Expression, MolQL)):
        return value.model_dump(exclude_none=True)
    if isinstance(value, list):
        return [_selector(item) for item in value]
    return value


def _focus(node: Any, value: bool | Focus) -> None:
    if value is True:
        node.focus()
    elif isinstance(value, Focus):
        node.focus(**value.model_dump(exclude_none=True))


def _annotation_call(node, method: str, data: AnnotationData):
    params = data.model_dump(by_alias=True, exclude_none=True)
    suffix = "from_uri" if data.uri is not None else "from_source"
    return getattr(node, f"{method}_{suffix}")(**params)


def _compile_primitives(structure, primitives):
    for item in primitives:
        params = item.model_dump(mode="json", exclude_none=True, exclude={"type"})
        tooltip = params.pop("tooltip", None)
        group = structure.primitives(**({"tooltip": tooltip} if tooltip else {}))
        getattr(group, item.type)(**params)


def _compile_layer(root, layer, legend, representation_specs):
    if layer.structure.url is None and layer.structure.format != "bcif":
        raise ValueError("A custom URL is required for formats other than bcif")
    layer.structure.url = (
        layer.structure.url
        or f"https://www.ebi.ac.uk/pdbe/entry-files/download/{layer.pdb_id}.bcif"
    )
    tables = [
        *layer.labels_from,
        *layer.tooltips_from,
        *[c.annotation for c in layer.components if c.annotation is not None],
        *[d for c in [*layer.components, *layer.annotations] for d in c.color_from],
    ]
    if layer.structure.format not in {"bcif", "mmcif"} and any(
        data.uri is None for data in tables
    ):
        raise ValueError("Source annotation tables require mmcif or bcif coordinates")
    parsed = root.download(url=layer.structure.url).parse(format=layer.structure.format)
    options = layer.structure
    params: dict[str, Any] = {"model_index": options.model_index}
    for key in ("block_index", "block_header", "ref"):
        if getattr(options, key) is not None:
            params[key] = getattr(options, key)
    if options.type == "assembly":
        params["assembly_id"] = options.assembly_id
    elif options.type == "symmetry":
        params.update(ijk_min=options.ijk_min, ijk_max=options.ijk_max)
    elif options.type == "symmetry_mates":
        params["radius"] = options.radius
    structure = getattr(parsed, f"{options.type}_structure")(**params)
    groups: dict[str, list[tuple[Annotation, Any]]] = {}
    if options.transform is not None:
        structure.transform(**options.transform.model_dump(exclude_none=True))
    for instance in options.instances:
        structure.instance(**instance.model_dump(exclude_none=True))
    for data in layer.labels_from:
        _annotation_call(structure, "label", data)
    for data in layer.tooltips_from:
        _annotation_call(structure, "tooltip", data)
    _compile_primitives(structure, layer.primitives)
    for item in [*layer.components, *layer.annotations]:
        selector = _selector(item.selector)
        expressions = selector if isinstance(selector, list) else [selector]
        if not layer.include_water and any(
            expression == "water"
            or (
                isinstance(expression, dict)
                and any(
                    str(expression.get(key, "")).upper() in {"HOH", "WAT"}
                    for key in ("label_comp_id", "auth_comp_id")
                )
            )
            for expression in expressions
        ):
            raise ValueError("Set include_water=true to explicitly display water")
        if selector == "all" and not layer.include_water:
            selectors: list[Any] = ["polymer", "branched", "ligand", "ion"]
        else:
            selectors = [selector]
        label = (
            item.label.text
            if item.label
            else "Annotation selection"
            if isinstance(item, Component) and item.annotation is not None
            else (
                item.selector
                if isinstance(item.selector, str)
                else "Selected component"
            )
        )
        # Match inline color order: an unconditional color replaces earlier
        # colors, while selector-specific colors add highlights on top.
        legend_colors = []
        for color in ([item.color] if item.color else []) + item.colors:
            if color.selector is None:
                legend_colors = []
            if color.color not in legend_colors:
                legend_colors.append(color.color)
        legend.append(
            {
                "label": label,
                **(
                    {
                        "annotation": item.annotation.model_dump(
                            mode="json", by_alias=True, exclude_none=True
                        )
                    }
                    if isinstance(item, Component) and item.annotation is not None
                    else {"selector": _selector(item.selector)}
                ),
                "representation": item.representation.type,
                "colors": legend_colors,
            }
        )
        for selector in selectors:
            component = (
                _annotation_call(structure, "component", item.annotation)
                if isinstance(item, Component) and item.annotation is not None
                else structure.component(selector=selector)
            )
            # Putty and box common clipping fields are newer than Python 1.8.
            # Apply validated viewer parameters after serializing below.
            rep = component.representation(
                type="backbone"
                if item.representation.type == "putty"
                else item.representation.type
            )
            representation_specs.append(item.representation)
            if item.representation.opacity is not None:
                rep.opacity(opacity=item.representation.opacity)
            for color in ([item.color] if item.color else []) + item.colors:
                rep.color(
                    color=color.color,
                    **(
                        {"selector": _selector(color.selector)}
                        if color.selector is not None
                        else {}
                    ),
                )
            for data in item.color_from:
                _annotation_call(rep, "color", data)
            if item.tooltip:
                component.tooltip(text=item.tooltip.text)
            if isinstance(item, Annotation) and item.group_id is not None:
                if not item.label:
                    raise ValueError("Grouped annotations require a label")
                groups.setdefault(item.group_id, []).append((item, selector))
            elif item.label and (
                item.label.scene
                or isinstance(selector, dict)
                and any(key in selector for key in ("label_seq_id", "auth_seq_id"))
            ):
                component.label(text=item.label.text)
            _focus(component, item.focus)
    for rows in groups.values():
        texts = {item.label.text for item, _ in rows if item.label}
        selectors = [selector for _, selector in rows]
        if len(texts) != 1 or not all(
            isinstance(selector, (dict, list)) for selector in selectors
        ):
            raise ValueError(
                "Grouped annotations require matching label text and expression selectors"
            )
        union = [
            expression
            for selector in selectors
            for expression in (selector if isinstance(selector, list) else [selector])
        ]
        structure.component(selector=union).label(text=next(iter(texts)))
    return structure


def _normalized_layer(layer):
    spec = layer.model_dump(mode="json", by_alias=True, exclude_none=True)
    spec["structure"] = layer.structure.model_dump(
        mode="json", by_alias=True, exclude_none=True, exclude_unset=True
    )
    for component in spec["components"]:
        if component.get("annotation") is not None:
            component.pop("selector", None)
    return spec


def build_mvs(arguments: dict[str, Any]) -> dict[str, Any]:
    """Compile a complete replacement scene; never execute caller-supplied code."""
    scene = BuildMvsInput.model_validate(arguments).builder
    scene.title = scene.title or f"MolViewSpec for {scene.pdb_id.upper()}"
    if scene.structure.url is None and scene.structure.format != "bcif":
        raise ValueError("A custom URL is required for formats other than bcif")
    scene.structure.url = (
        scene.structure.url
        or f"https://www.ebi.ac.uk/pdbe/entry-files/download/{scene.pdb_id}.bcif"
    )
    root = create_builder()
    root.canvas(**scene.canvas.model_dump())
    if scene.camera:
        root.camera(**scene.camera.model_dump())
    legend = []
    warnings = [
        "Scene selections and descriptions are caller-supplied; compilation does not verify biological claims."
    ]
    representation_specs: list[Representation] = []
    for layer in [scene, *scene.additional_structures]:
        structure = _compile_layer(root, layer, legend, representation_specs)
        if layer is not scene and layer.focus:
            _focus(structure.component(selector="all"), layer.focus)
    for volume_spec in scene.volumes:
        volume = (
            root.download(url=volume_spec.url)
            .parse(format=volume_spec.format)
            .volume(channel_id=volume_spec.channel_id)
        )
        rep = volume.representation(
            type="isosurface",
            **volume_spec.representation.model_dump(exclude_none=True),
        )
        if volume_spec.color:
            rep.color(color=volume_spec.color)
        if volume_spec.opacity is not None:
            rep.opacity(opacity=volume_spec.opacity)
        legend.append(
            {
                "label": volume_spec.channel_id or "Density",
                "representation": "isosurface",
                "colors": [volume_spec.color] if volume_spec.color else [],
            }
        )
    _focus(root, scene.focus)
    mvsj = json.loads(
        root.get_state(
            title=scene.title,
            description=scene.description,
            description_format=scene.description_format,
        ).model_dump_json(exclude_none=True, by_alias=True)
    )
    specs = iter(representation_specs)

    def viewer_parameters(node):
        if node["kind"] == "representation":
            spec = next(specs)
            node["params"] = spec.model_dump(
                mode="json", exclude_none=True, exclude={"opacity", "clip"}
            )
            clips = (
                spec.clip
                if isinstance(spec.clip, list)
                else ([spec.clip] if spec.clip else [])
            )
            for clip in clips:
                node.setdefault("children", []).append(
                    {
                        "kind": "clip",
                        "params": clip.model_dump(
                            mode="json", by_alias=True, exclude_none=True
                        ),
                    }
                )
        for child in node.get("children", []):
            viewer_parameters(child)

    viewer_parameters(mvsj["root"])
    normalized = _normalized_layer(scene)
    normalized["additional_structures"] = [
        _normalized_layer(layer) for layer in scene.additional_structures
    ]
    return {
        "version": 1,
        "builder": normalized,
        "mvsj": mvsj,
        "legend": legend,
        "warnings": warnings,
        "coordinate_url": scene.structure.url,
        "sources": list(
            dict.fromkeys(
                [
                    *[
                        layer.structure.url
                        for layer in [scene, *scene.additional_structures]
                    ],
                    *[volume.url for volume in scene.volumes],
                    *[
                        url
                        for layer in [scene, *scene.additional_structures]
                        for url in layer.sources
                    ],
                    *[
                        data.uri
                        for layer in [scene, *scene.additional_structures]
                        for data in [
                            *layer.labels_from,
                            *layer.tooltips_from,
                            *[
                                c.annotation
                                for c in layer.components
                                if c.annotation is not None
                            ],
                            *[
                                d
                                for c in [*layer.components, *layer.annotations]
                                for d in c.color_from
                            ],
                        ]
                        if data.uri is not None
                    ],
                ]
            )
        ),
    }
