from anime_extensions.utils.unpacker import unpack_packer


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
    # This packed string decodes to: "Hello World"
    # Using uppercase characters in the dictionary indices (radix-62)
    packed = r"eval(function(p,a,c,k,e,d){e=function(c){return(c<a?'':e(parseInt(c/a)))+((c=c%a)>35?String.fromCharCode(c+29):c.toString(36))};if(!''.replace(/^/,String)){while(c--){d[e(c)]=k[c]||e(c)}k=[function(e){return d[e]}];e=function(){return'\w+'};c=1};while(c--){if(k[c]){p=p.replace(new RegExp('\b'+e(c)+'\b','g'),k[c])}}return p}('0 1()',2,2,'Hello|World|console'.split('|'),0,{}))"
    unpacked = unpack_packer(packed)
    assert unpacked == "Hello World()"
