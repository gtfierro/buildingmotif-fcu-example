from collections import defaultdict
from pathlib import Path
from functools import cached_property
from typing import Callable, Dict, List, Set
from buildingmotif import BuildingMOTIF
from buildingmotif.dataclasses import Library, Model
from buildingmotif.ingresses import CSVIngress, TemplateIngress
from buildingmotif.ingresses.base import Record, RecordIngressHandler
from rdflib import Namespace, RDFS, Literal, RDF

GroupFn = Callable[[Record], str]

class FCUPointImporter(RecordIngressHandler):
    def __init__(self, csv: CSVIngress, group_key: GroupFn):
        self.groups = defaultdict(set)
        for record in csv.records:
            key = group_key(record)
            self.groups[key].add(record.fields.get('point'))

    @cached_property
    def records(self) -> List[Record]:
        records = []

        lookup = {
            "ChwVlvPos": "chw_coil-position",
            "HwVlvPos": "hw_coil-position",
            "RoomTmp": "room-temp",
            "Room_RH": "room-relative_humidity",
            "UnoccHtgSpt": "unocc_htg_sp",
            "OccHtgSpt": "occ_htg_sp",
            "UnoccClgSpt": "unocc_clg_sp",
            "OccClgSpt": "occ_clg_sp",
            "SaTmp": "supply_temp",
            "OccCmd": "occ_cmd",
            "EffOcc": "occ_status",
        }
        for key, points in self.groups.items():
            bindings = {'name': key, 'room': key[3:]}
            for point in points:
                for suffix, param in lookup.items():
                    if point.endswith(suffix):
                        bindings[param] = point
                        break
            rec = Record(
                    rtype=key,
                    fields=bindings,
            )
            records.append(rec)

        return records


def fcu_group_function(rec: Record) -> str:
    pointname = rec.fields.get("point")
    assert pointname is not None, "needs 'point' column"
    parts = pointname.split(':')
    equip_part = parts[-1]
    if not equip_part[:3] == 'FCU':
        return ''
    return equip_part[:6]

csv_ing = CSVIngress(Path("fcu_points.csv"))
point_importer_ing = FCUPointImporter(csv_ing, fcu_group_function)

bm = BuildingMOTIF("sqlite:///bm.db")
bm.setup_tables()

BLDG = Namespace("urn:building1/")
model = Model.create(BLDG)

brick = Library.load(ontology_graph="Brick.ttl", overwrite=False)
templates = Library.load(directory="templates", overwrite=True)
fcu_temp = templates.get_template_by_name("fcu").inline_dependencies()

templ_ing = TemplateIngress(fcu_temp, None, point_importer_ing, inline=True)
g = templ_ing.graph(BLDG)

# add labels
for rec in csv_ing.records:
    point = rec.fields['point']
    if (BLDG[point], RDF.type, None) in g:
        g.add((BLDG[point], RDFS.label, Literal(point)))

model.add_graph(g)

bm.session.commit()

model.graph.serialize('building1.ttl')
