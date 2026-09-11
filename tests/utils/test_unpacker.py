"""Unit tests for Unpacker utility."""

from anime_extensions.utils.unpacker import Unpacker, unpack_packer


def test_unpacker_is_packed():
    assert Unpacker.is_packed("eval(function(p,a,c,k,e,d)")
    assert Unpacker.is_packed("eval(function(p,a,c,k,e,r)")
    assert not Unpacker.is_packed("console.log('hi');")


def test_unpack():
    packed = r"""eval(function(p,a,c,k,e,d){e=function(c){return c};if(!''.replace(/^/,String)){while(c--){d[c]=k[c]||c}k=[function(e){return d[e]}];e=function(){return'\\w+'};c=1};while(c--){if(k[c]){p=p.replace(new RegExp('\\b'+e(c)+'\\b','g'),k[c])}}return p}('0.1(\'2\');',3,3,'console|log|hello'.split('|'),0,{}))"""
    unpacked = Unpacker.unpack(packed)
    assert "console.log('hello');" in unpacked


def test_unpack_packer_simple():
    packed = r"eval(function(p,a,c,k,e,d){e=function(c){return c};if(!''.replace(/^/,String)){while(c--){d[c]=k[c]||c}k=[function(e){return d[e]}];e=function(){return'\\w+'};c=1};while(c--){if(k[c]){p=p.replace(new RegExp('\\b'+e(c)+'\\b','g'),k[c])}}return p}('0 1 2()',3,3,'console|log|test'.split('|'),0,{}))"
    unpacked = unpack_packer(packed)
    assert unpacked == "console log test()"


def test_unpack_packer_complex():
    packed = r"eval(function(p,a,c,k,e,d){e=function(c){return(c<a?'':e(parseInt(c/a)))+((c=c%a)>35?String.fromCharCode(c+29):c.toString(36))};if(!''.replace(/^/,String)){while(c--){d[e(c)]=k[c]||e(c)}k=[function(e){return d[e]}];e=function(){return'\\w+'};c=1};while(c--){if(k[c]){p=p.replace(new RegExp('\\b'+e(c)+'\\b','g'),k[c])}}return p}('0.1(\'2 3!\');',4,4,'console|log|Hello|World'.split('|'),0,{}))"
    unpacked = unpack_packer(packed)
    assert unpacked == "console.log('Hello World!');"


def test_unpack_packer_no_match():
    assert unpack_packer("console.log('not packed')") is None


def test_unpack_packer_empty():
    assert unpack_packer("") is None


def test_unpack_packer_radix62_uppercase():
    """Test Dean Edwards packer with uppercase radix-62 encoded strings."""
    packed = r"eval(function(p,a,c,k,e,d){e=function(c){return(c<a?'':e(parseInt(c/a)))+((c=c%a)>35?String.fromCharCode(c+29):c.toString(36))};if(!''.replace(/^/,String)){while(c--){d[e(c)]=k[c]||e(c)}k=[function(e){return d[e]}];e=function(){return'\w+'};c=1};while(c--){if(k[c]){p=p.replace(new RegExp('\b'+e(c)+'\b','g'),k[c])}}return p}('0 1()',2,2,'Hello|World|console'.split('|'),0,{}))"
    unpacked = unpack_packer(packed)
    assert unpacked == "Hello World()"


def test_radix_str():
    assert Unpacker._radix_str(0, 10) == "0"
    assert Unpacker._radix_str(10, 10) == "10"
    assert Unpacker._radix_str(10, 16) == "a"
