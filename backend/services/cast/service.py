"""Cast — the ensemble for a film: script roles mapped to avatars and voices.

A film is written with named roles ("ARIA", "KAI"). The cast block binds each role
name to one of the user's avatars (a Character) and a voice, so the director and the
composition layer know who appears in a scene, in which look, speaking in which voice.
This is what turns "render a scene" into "render a script with a cast of one or many
people, each consistent across shots."

The cast service validates that every avatar referenced is owned by the requesting
user (no borrowing another account's avatars) and resolves per-role content policy
(a real-person role must route to a reference-capable engine), which composition
then honours scene by scene.
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional

from backend.services.character.service import CharacterService, get_character_service


class CastError(Exception):
    def __init__(self, message: str, status_code: int = 422):
        super().__init__(message)
        self.status_code = status_code


@dataclass
class CastMember:
    """One role in the script, bound to an avatar and a voice."""

    role: str  # the name used in the script, e.g. "ARIA"
    avatar_id: str  # a Character owned by the user
    voice: str = ""  # voice id or a described voice (resolved elsewhere)
    # resolved at bind time from the avatar:
    style: str = "realistic"
    is_real_person: bool = True
    display_name: str = ""


@dataclass
class Cast:
    members: List[CastMember] = field(default_factory=list)

    def by_role(self) -> Dict[str, CastMember]:
        return {m.role.upper(): m for m in self.members}

    def member_for(self, role: str) -> Optional[CastMember]:
        return self.by_role().get((role or "").upper())

    @property
    def any_real_person(self) -> bool:
        return any(m.is_real_person for m in self.members)


class CastService:
    def __init__(self, characters: Optional[CharacterService] = None):
        self.characters = characters or get_character_service()

    async def bind(self, user_id: str, members: List[dict]) -> Cast:
        """Validate + resolve a cast block against the user's owned avatars.

        Each member dict: {role, avatar_id, voice?}. Every avatar must exist and be
        owned by user_id; role names must be unique. Returns a resolved Cast whose
        members carry the avatar's style/real-person flag for downstream routing.
        """
        if not members:
            raise CastError("Cast is empty — add at least one role")
        seen_roles = set()
        resolved: List[CastMember] = []
        for raw in members:
            role = str(raw.get("role", "")).strip()
            avatar_id = str(raw.get("avatar_id", "")).strip()
            if not role:
                raise CastError("Every cast member needs a role name")
            if role.upper() in seen_roles:
                raise CastError(f"Duplicate role name: {role}")
            seen_roles.add(role.upper())
            if not avatar_id:
                raise CastError(f"Role '{role}' has no avatar")
            char = await self.characters.get(avatar_id)
            if char is None or char.user_id != user_id:
                raise CastError(f"Avatar for role '{role}' not found", status_code=404)
            resolved.append(
                CastMember(
                    role=role,
                    avatar_id=avatar_id,
                    voice=str(raw.get("voice", "")).strip(),
                    style=char.default_style,
                    is_real_person=bool(char.is_real_person),
                    display_name=char.name,
                )
            )
        return Cast(members=resolved)


def get_cast_service() -> CastService:
    return CastService()
