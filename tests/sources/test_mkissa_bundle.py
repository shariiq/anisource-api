"""Deterministic tests for the MKissa frontend crypto-bundle parser."""

from anime_extensions.sources.mkissa.bundle import MKissaBundle


def test_parse_decodes_rotated_build_and_seed_table() -> None:
    """Resolve the build ID and four base64 seed fragments at one rotation."""
    bundle = """
function tbl(){const values=["junk","12345","QUFBQ","UFBQUE=","QkJCQ","kJCQkI=","Q0NDQ","0NDQ0M=","RERER","EREREQ="]}
function base(value){return value=value-(10),tbl()[value]}
function alias(first,second){return base(first+0)}
function target(mask=build){return mask}
build=alias(11);
sf=1;
seeds=[alias(12)+alias(13),alias(14)+alias(15),alias(16)+alias(17),alias(18)+alias(19)]
"""

    build = MKissaBundle.parse(bundle)

    assert build is not None
    assert build.build_id == "12345"
    assert build.seeds == ("QUFBQUFBQUE=", "QkJCQkJCQkI=", "Q0NDQ0NDQ0M=", "REREREREREQ=")


def test_parse_rejects_bundle_without_complete_seed_material() -> None:
    """Avoid accepting a numeric table value without a valid seed expression."""
    bundle = """
function tbl(){const values=["junk","12345"]}
function base(value){return value=value-(10),tbl()[value]}
function alias(first,second){return base(first+0)}
build=alias(11);
"""

    assert MKissaBundle.parse(bundle) is None


def test_parse_dynamic_config_and_sixteen_fragment_seeds() -> None:
    """Resolve four seeds divided into sixteen fragments, and dynamic Mf config constants."""
    bundle = """
function tbl(){const values=["junk","build-167","QU","FB","QU","FBQUE=","Qk","JC","Qk","JCQkI=","Q0","ND","Q0","NDQ0M=","RE","RE","RE","REREQ=","JX","Ht","yI","w","lane","epoch","group","host","buildId"]}
function base(value){return value=value-(10),tbl()[value]}
function alias(first,second){return base(first+0)}
build=alias(11);
const dm=[alias(12)+alias(13)+alias(14)+alias(15),alias(16)+alias(17)+alias(18)+alias(19),alias(20)+alias(21)+alias(22)+alias(23),alias(24)+alias(25)+alias(26)+alias(27)]
Mf={v:1,saltMul:114,saltAdd:200,fragMul:219,fragAdd:67,bootPrefix:alias(28)+alias(29)+alias(30)+alias(31)+":",join:"~",parts:[alias(32),alias(33),alias(34),alias(35),alias(36)],omitEmptyLane:!1,envXor:72};
"""

    build = MKissaBundle.parse(bundle)

    assert build is not None
    assert build.build_id == "build-167"
    assert build.seeds == ("QUFBQUFBQUE=", "QkJCQkJCQkI=", "Q0NDQ0NDQ0M=", "REREREREREQ=")

    config = build.config
    assert config is not None
    assert config.salt_mul == 114
    assert config.salt_add == 200
    assert config.frag_mul == 219
    assert config.frag_add == 67
    assert config.boot_prefix == "JXHtyIw:"
    assert config.join_char == "~"
    assert config.parts == ("lane", "epoch", "group", "host", "buildId")
    assert config.env_xor == 72
