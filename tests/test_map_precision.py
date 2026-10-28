import gzip,struct,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from jarvis.vector_city import decode_tile,polygon_groups
from jarvis.config import Settings
from jarvis.city_data import tile_zoom_for_bounds

def vi(value):
 out=bytearray()
 while value>127:out.append((value&127)|128);value>>=7
 out.append(value);return bytes(out)
def field(n,data):return vi((n<<3)|2)+vi(len(data))+data
def zig(value):return (value<<1)^(value>>63)
def geometry(rings):
 out=[];x=y=0
 for ring in rings:
  first,*rest=ring
  out.extend((9,zig(first[0]-x),zig(first[1]-y)));x,y=first
  out.append((len(rest)<<3)|2)
  for a,b in rest:out.extend((zig(a-x),zig(b-y)));x,y=a,b
  out.append(15)
 return b"".join(vi(n) for n in out)
def tile(rings,height=42,bottom=9,hide=False):
 props=[("render_height",vi((3<<3)|1)+struct.pack("<d",height)),("render_min_height",vi((3<<3)|1)+struct.pack("<d",bottom)),("hide_3d",vi(7<<3)+vi(int(hide)))]
 tags=b"".join(vi(i)+vi(i) for i in range(len(props)))
 feature=vi(8)+vi(42)+field(2,tags)+vi(24)+vi(3)+field(4,geometry(rings))
 layer=field(1,b"building")+field(2,feature)
 for name,value in props:layer+=field(3,name.encode())+field(4,value)
 return field(3,layer+vi(40)+vi(4096)+vi(120)+vi(2))
class MapPrecisionTests(unittest.TestCase):
 def setUp(self):
  self.outer=[(0,0),(200,0),(200,200),(0,200)]
  self.hole=[(50,50),(50,150),(150,150),(150,50)]
 def test_inner_ring_remains_a_hole(self):
  data=decode_tile(tile([self.outer,self.hole]),13600,6690,14)
  self.assertEqual(len(data["buildings"]),1)
  self.assertEqual(len(data["buildings"][0]["holes"]),1)
  self.assertEqual(data["buildings"][0]["height"],42)
  self.assertEqual(data["buildings"][0]["min_height"],9)
  self.assertEqual(data["buildings"][0]["height_source"],"provider_approximation")
 def test_hidden_outline_is_not_a_second_tower(self):
  self.assertEqual(decode_tile(tile([self.outer],hide=True),13600,6690,14)["buildings"],[])
 def test_gzipped_tile_keeps_identical_geometry(self):
  raw=tile([self.outer,self.hole])
  self.assertEqual(decode_tile(raw,13600,6690,14),decode_tile(gzip.compress(raw),13600,6690,14))
 def test_multiple_polygons_keep_separate_holes(self):
  second=[(400,0),(600,0),(600,200),(400,200)]
  data=decode_tile(tile([self.outer,self.hole,second]),13600,6690,14)
  self.assertEqual(len(data["buildings"]),2)
  self.assertEqual([len(p["holes"]) for p in data["buildings"]],[1,0])
 def test_scale_settings_reject_invalid_and_nonfinite_values(self):
  for value in ("nan","inf","abc","0","33"):
   with self.subTest(value=value),self.assertRaises(ValueError):Settings(MAP_HEIGHT_SCALE=value).validated()
  for value in ("500","5001","nan"):
   with self.subTest(value=value),self.assertRaises(ValueError):Settings(MAP_VIEW_METERS=value).validated()
 def test_map_settings_default_to_closer_and_taller_view(self):
  s=Settings().validated()
  self.assertEqual(s.MAP_VIEW_METERS,"1600");self.assertEqual(s.MAP_HEIGHT_SCALE,"16")

class WideMapTests(unittest.TestCase):
 def test_large_overview_chooses_tiles_covering_the_whole_area(self):
  self.assertLess(tile_zoom_for_bounds([31.1,120.4,31.5,120.9],True),14)
 def test_local_details_keep_source_maximum_zoom(self):
  self.assertEqual(tile_zoom_for_bounds([31.2,120.6,31.21,120.61]),14)
