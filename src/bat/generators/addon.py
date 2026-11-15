"""Add-on generator facade.

Every method delegates to a single template module and returns a
:class:`GeneratedFile` describing exactly what was written. Generators never
report success for a feature the target version cannot support: compatibility is
checked before content is emitted.
"""

from __future__ import annotations

from typing import Any

from ..core.models import GeneratedFile, PackKind
from . import animation as animation_templates
from . import attachable as attachable_templates
from . import block as block_templates
from . import entity as entity_templates
from . import item as item_templates
from . import loot_table as loot_templates
from . import particle as particle_templates
from . import recipe as recipe_templates
from . import script as script_templates
from . import spawn_rule as spawn_templates
from .common import GenerationContext


class AddonGenerator:
    def __init__(self, context: GenerationContext) -> None:
        self.context = context

    # -- packs -------------------------------------------------------------
    def create_addon(self) -> list[GeneratedFile]:
        """Ensure both packs exist and return their manifests."""
        behavior = self.context.primary_pack(PackKind.BEHAVIOR)
        resource = self.context.primary_pack(PackKind.RESOURCE)
        files = []
        for kind, pack in ((PackKind.BEHAVIOR, behavior), (PackKind.RESOURCE, resource)):
            manifest = pack / "manifest.json"
            files.append(
                GeneratedFile(
                    path=manifest.relative_to(
                        self.context.projects.files_root(self.context.project.project_id)
                    ).as_posix(),
                    kind="manifest.format_version_2",
                    pack=pack.name,
                    description=f"{kind.value.title()} pack manifest",
                )
            )
        self.context.touch()
        return files

    # -- content -----------------------------------------------------------
    def create_entity(self, **kwargs: Any) -> GeneratedFile:
        return entity_templates.create_entity(self.context, **kwargs)

    def create_block(self, **kwargs: Any) -> GeneratedFile:
        return block_templates.create_block(self.context, **kwargs)

    def create_item(self, **kwargs: Any) -> GeneratedFile:
        return item_templates.create_item(self.context, **kwargs)

    def create_recipe(self, **kwargs: Any) -> GeneratedFile:
        return recipe_templates.create_recipe(self.context, **kwargs)

    def create_loot_table(self, **kwargs: Any) -> GeneratedFile:
        return loot_templates.create_loot_table(self.context, **kwargs)

    def create_spawn_rule(self, **kwargs: Any) -> GeneratedFile:
        return spawn_templates.create_spawn_rule(self.context, **kwargs)

    def create_animation(self, **kwargs: Any) -> GeneratedFile:
        return animation_templates.create_animation(self.context, **kwargs)

    def create_animation_controller(self, **kwargs: Any) -> GeneratedFile:
        return animation_templates.create_animation_controller(self.context, **kwargs)

    def create_particle(self, **kwargs: Any) -> GeneratedFile:
        return particle_templates.create_particle(self.context, **kwargs)

    def create_attachable(self, **kwargs: Any) -> GeneratedFile:
        return attachable_templates.create_attachable(self.context, **kwargs)

    def create_script_module(self, **kwargs: Any) -> GeneratedFile:
        return script_templates.create_script_module(self.context, **kwargs)
