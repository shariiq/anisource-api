"""Unit tests for Unpacker utility."""

from anime_extensions.utils.unpacker import Unpacker


def test_unpacker_is_packed():
    assert Unpacker.is_packed("eval(function(p,a,c,k,e,d)")
    assert Unpacker.is_packed("eval(function(p,a,c,k,e,r)")
    assert not Unpacker.is_packed("console.log('hi');")


def test_unpack():
    packed = r"""eval(function(p,a,c,k,e,d){e=function(c){return c};if(!''.replace(/^/,String)){while(c--){d[c]=k[c]||c}k=[function(e){return d[e]}];e=function(){return'\\w+'};c=1};while(c--){if(k[c]){p=p.replace(new RegExp('\\b'+e(c)+'\\b','g'),k[c])}}return p}('0.1(\'2\');',3,3,'console|log|hello'.split('|'),0,{}))"""
    unpacked = Unpacker.unpack(packed)
    assert "console.log('hello');" in unpacked


def test_radix_str():
    assert Unpacker._radix_str(0, 10) == "0"
    assert Unpacker._radix_str(10, 10) == "10"
    assert Unpacker._radix_str(10, 16) == "a"
