# Copyright (c) 2026, rndops and contributors
# For license information, please see license.txt

"""
Maps the Academic API's free-text `d_name` (e.g. "Department of Computer
Science and Engineering") to the corresponding `Department_prornd` docname
in this system.

The Academic API's `d_name` values don't line up 1:1 with our
`Department_prornd.dept_name` labels (different prefixes, abbreviations,
school vs. department naming), so this is a hardcoded lookup rather than a
live query. Keys are the exact `d_name` strings observed from the API;
values are `Department_prornd` docnames (the hashed `name` field, since
`User.department_name` links to that).

A handful of `d_name` values (interdisciplinary programs, "Liberal Arts",
"Bioengineering", "Electronic Product Design") have no unambiguous match in
Department_prornd and are intentionally left unmapped below.
"""

ACADEMIC_DEPARTMENT_MAP = {
	"Department of Electronics and Electrical Engineering": "otg9mgi2qo",
	"Department of Mechanical Engineering": "oth70m1u93",
	"Department of Civil Engineering": "otho2cn3vc",
	"Department of Computer Science and Engineering": "otg4tn5qak",
	"Department of Chemistry": "oti38qjrhn",
	"Department of Chemical Engineering": "otgh263a0u",
	"Department of Biosciences and Bioengineering": "otf8u12lt1",
	"Department of Physics": "oti8os9ndm",
	"Department of Mathematics": "otf4r0vk5i",
	"Department of Design": "oti70914lt",
	"Department of Humanities and Social Sciences": "otg0njv9fe",
	"School of Energy Science and Engineering": "q8rn68543h",
	"MF School of Data Science and Artificial Intelligence": "otinash320",
	"JBM School of Health Sciences and Technology": "otikrccdte",
	"Center for Intelligent Cyber Physical Systems": "othgfehjn4",
	"School of Business": "oticcb7n4k",
	"School of Agro and Rural Technology": "othbgm33i1",
	"School of Interdisciplinary Studies and Sustainability": "o4mhu75tlt",
	"Centre for Nanotechnology": "otfh96rr10",
	"Centre for Linguistic Science and Technology": "othpf5n59o",
	"Centre for Disaster Management and Research": "othti7hf3b",
	"Centre for Sustainable Polymers": "otin0bjjbs",
	"Centre for Indian Knowledge Systems": "othmo6amjt",
	"Centre for Sustainable Water Research": "otiv33v94b",
	"Centre for Drone Technology": "otice37v39",
}


def map_academic_department(d_name):
	"""Return the Department_prornd docname for an Academic API `d_name`, or None."""
	return ACADEMIC_DEPARTMENT_MAP.get(str(d_name or "").strip())
