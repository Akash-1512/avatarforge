"""Cast binding + cast-aware director/composition routing."""

import pytest

from backend.services.cast.service import Cast, CastError, CastMember, CastService
from backend.services.composition.service import CompositionService
from backend.services.director.service import Scene, Storyboard
from backend.services.scene.service import SceneService


class _Char:
    def __init__(self, id, user_id, style="realistic", real=True, name="X"):
        self.id = id
        self.user_id = user_id
        self.default_style = style
        self.is_real_person = real
        self.name = name


class _Chars:
    def __init__(self, chars):
        self._c = {c.id: c for c in chars}

    async def get(self, cid):
        return self._c.get(cid)


@pytest.mark.asyncio
async def test_bind_resolves_owned_avatars():
    chars = _Chars(
        [
            _Char("a1", "u1", "anime", real=False, name="Aria"),
            _Char("a2", "u1", "realistic", real=True, name="Kai"),
        ]
    )
    cast = await CastService(chars).bind(
        "u1",
        [
            {"role": "ARIA", "avatar_id": "a1", "voice": "v1"},
            {"role": "KAI", "avatar_id": "a2"},
        ],
    )
    assert len(cast.members) == 2
    assert cast.member_for("aria").style == "anime"  # case-insensitive
    assert cast.member_for("KAI").is_real_person is True
    assert cast.any_real_person is True


@pytest.mark.asyncio
async def test_bind_rejects_unowned_avatar():
    chars = _Chars([_Char("a1", "OTHER_USER")])
    with pytest.raises(CastError) as ei:
        await CastService(chars).bind("u1", [{"role": "X", "avatar_id": "a1"}])
    assert ei.value.status_code == 404


@pytest.mark.asyncio
async def test_bind_rejects_duplicate_roles():
    chars = _Chars([_Char("a1", "u1"), _Char("a2", "u1")])
    with pytest.raises(CastError):
        await CastService(chars).bind(
            "u1", [{"role": "HOST", "avatar_id": "a1"}, {"role": "host", "avatar_id": "a2"}]
        )


@pytest.mark.asyncio
async def test_bind_rejects_empty_cast():
    with pytest.raises(CastError):
        await CastService(_Chars([])).bind("u1", [])


class _Engine:
    def __init__(self, name, real):
        self.name = name
        self.accepts_real_face = real
        self.prompts = []

    async def generate(self, prompt, seconds=4, size="1280x720", reference_image=None):
        self.prompts.append(prompt)
        return b"CLIP"


@pytest.mark.asyncio
async def test_cast_render_routes_real_person_to_reference_engine():
    sora = _Engine("sora2", False)
    kling = _Engine("kling", True)
    svc = CompositionService(
        SceneService(engines={"sora2": sora, "kling": kling}, default_engine="sora2")
    )
    cast = Cast(
        members=[
            CastMember(role="ARIA", avatar_id="a1", style="anime", is_real_person=False),
            CastMember(role="KAI", avatar_id="a2", style="realistic", is_real_person=True),
        ]
    )
    board = Storyboard(
        title="T",
        style="anime",
        scenes=[
            Scene(shot="aria waves", camera="static", dialogue="", seconds=4, role="ARIA"),
        ],
    )
    kai_board = Storyboard(
        title="T",
        style="anime",
        scenes=[
            Scene(shot="kai speaks", camera="static", dialogue="hi", seconds=4, role="KAI"),
        ],
    )

    # single-scene boards isolate routing from the stitch (covered in test_composition)
    async def fake_loader(avatar_id):
        return b"\xff\xd8refframe"

    aria_res = await svc.render_with_cast(board, cast, reference_loader=fake_loader)
    kai_res = await svc.render_with_cast(kai_board, cast, reference_loader=fake_loader)
    # the real-person KAI scene must have gone to the reference-capable engine
    assert kai_res.clips[0].engine == "kling"
    # the stylized ARIA scene to sora2, rendered in her style
    assert aria_res.clips[0].engine == "sora2"
    assert "anime style" in sora.prompts[0]


@pytest.mark.asyncio
async def test_cast_render_no_role_uses_board_style():
    sora = _Engine("sora2", False)
    svc = CompositionService(SceneService(engines={"sora2": sora}, default_engine="sora2"))
    cast = Cast(
        members=[CastMember(role="ARIA", avatar_id="a1", style="anime", is_real_person=False)]
    )
    board = Storyboard(
        title="T",
        style="pixar",
        scenes=[
            Scene(
                shot="establishing shot of a city", camera="wide", dialogue="", seconds=4, role=""
            ),
        ],
    )

    async def fake_loader(_):
        return b"\xff\xd8ref"

    result = await svc.render_with_cast(board, cast, reference_loader=fake_loader)
    assert result.clips[0].engine == "sora2"
    assert "pixar style" in sora.prompts[0]  # board style, no member


def test_director_parses_role_field():
    from backend.services.director.service import DirectorService

    board = DirectorService._parse(
        '{"title":"T","style":"anime","scenes":['
        '{"shot":"aria waves","camera":"static","dialogue":"","seconds":4,"role":"ARIA"}]}'
    )
    assert board is not None and board.scenes[0].role == "ARIA"
