"""Cambridge (CIE), IB Diploma and NBT qualifications: Drive layout, catalogue keys and syllabus topic columns."""
from typing import List, Optional

T_MATH = ["Number", "Algebra & Graphs", "Coordinate Geometry", "Geometry", "Mensuration", "Trigonometry",
          "Transformations & Vectors", "Probability", "Statistics"]
T_ADD = ["Functions", "Quadratic Functions", "Factors of Polynomials", "Equations, Inequalities & Graphs", "Simultaneous Equations",
         "Logarithmic & Exponential Functions", "Straight-Line Graphs", "Coordinate Geometry of the Circle", "Circular Measure",
         "Trigonometry", "Permutations & Combinations", "Series", "Calculus"]
T_PHY = ["Motion, Forces & Energy", "Thermal Physics", "Waves", "Electricity & Magnetism", "Nuclear Physics", "Space Physics"]
T_CHEM = ["States of Matter", "Atoms, Elements & Compounds", "Stoichiometry", "Electrochemistry", "Chemical Energetics",
          "Chemical Reactions", "Acids, Bases & Salts", "The Periodic Table", "Metals", "Chemistry of the Environment",
          "Organic Chemistry", "Experimental Techniques & Chemical Analysis"]
T_BIO = ["Characteristics & Classification of Organisms", "Organisation of the Organism", "Movement In & Out of Cells",
         "Biological Molecules", "Enzymes", "Plant Nutrition", "Human Nutrition", "Transport in Plants", "Transport in Animals",
         "Gas Exchange & Respiration", "Coordination & Response", "Reproduction", "Organisms & Their Environment"]
T_SCI = [f"Biology - {t}" for t in T_BIO] + [f"Chemistry - {t}" for t in T_CHEM] + [f"Physics - {t}" for t in T_PHY]
P1_9709 = ["Quadratics", "Functions", "Coordinate Geometry", "Circular Measure", "Trigonometry", "Series", "Differentiation", "Integration"]
P3_9709 = ["Algebra", "Logarithmic & Exponential Functions", "Trigonometry", "Differentiation", "Integration",
           "Numerical Solution of Equations", "Vectors", "Differential Equations", "Complex Numbers"]
MECH = ["Forces & Equilibrium", "Kinematics of Motion in a Straight Line", "Momentum", "Newton's Laws of Motion", "Energy, Work & Power"]
PS1 = ["Representation of Data", "Permutations & Combinations", "Probability", "Discrete Random Variables", "The Normal Distribution"]
PS2 = ["The Poisson Distribution", "Linear Combinations of Random Variables", "Continuous Random Variables", "Sampling & Estimation", "Hypothesis Tests"]
T_9231 = {"1": ["Roots of Polynomial Equations", "Rational Functions & Graphs", "Summation of Series", "Matrices", "Polar Coordinates", "Vectors", "Proof by Induction"],
          "2": ["Hyperbolic Functions", "Matrices", "Differentiation", "Integration", "Complex Numbers", "Differential Equations"],
          "3": ["Motion of a Projectile", "Equilibrium of a Rigid Body", "Circular Motion", "Hooke's Law", "Linear Motion under a Variable Force", "Momentum"],
          "4": ["Continuous Random Variables", "Inference using Normal & t-Distributions", "Chi-Squared Tests", "Non-Parametric Tests", "Probability Generating Functions"]}
T_9702 = ["Physical Quantities & Units", "Kinematics", "Dynamics", "Forces, Density & Pressure", "Work, Energy & Power", "Deformation of Solids",
          "Waves", "Superposition", "Electricity", "D.C. Circuits", "Particle Physics", "Motion in a Circle", "Gravitational Fields",
          "Temperature", "Ideal Gases", "Thermodynamics", "Oscillations", "Electric Fields", "Capacitance", "Magnetic Fields",
          "Alternating Currents", "Quantum Physics", "Nuclear Physics", "Medical Physics", "Astronomy & Cosmology"]
T_9701 = ["Atomic Structure", "Atoms, Molecules & Stoichiometry", "Chemical Bonding", "States of Matter", "Chemical Energetics",
          "Electrochemistry", "Equilibria", "Reaction Kinetics", "The Periodic Table: Chemical Periodicity", "Group 2", "Group 17",
          "Nitrogen & Sulfur", "Hydrocarbons", "Halogen Compounds", "Hydroxy Compounds", "Carbonyl Compounds",
          "Carboxylic Acids & Derivatives", "Nitrogen Compounds", "Polymerisation", "Organic Synthesis", "Analytical Techniques",
          "Entropy & Gibbs Free Energy", "Chemistry of Transition Elements", "Arenes"]
T_CP_MATH = ["Number", "Algebra", "Geometry & Measure", "Statistics & Probability"]
T_CP_SCI = ["Biology", "Chemistry", "Physics", "Earth & Space", "Thinking & Working Scientifically"]
T_IB_MATH = ["Number & Algebra", "Functions", "Geometry & Trigonometry", "Statistics & Probability", "Calculus"]
T_IB_PHY = ["A. Space, Time & Motion", "B. The Particulate Nature of Matter", "C. Wave Behaviour", "D. Fields", "E. Nuclear & Quantum Physics"]
T_IB_CHEM = ["Structure 1: Particulate Nature of Matter", "Structure 2: Bonding & Structure", "Structure 3: Classification of Matter",
             "Reactivity 1: What Drives Reactions", "Reactivity 2: How Much, How Fast, How Far", "Reactivity 3: Mechanisms of Change"]

CIE_SERIES = {"Feb/Mar": "Feb-Mar", "May/Jun": "May-June", "Nov": "Oct-Nov"}
CP_SERIES = {"Apr": "April", "Oct": "October"}
IB_SESSIONS = {"May/Jun": "May", "Nov": "November"}


def _q(code, subject, level, label, papers, topics, series=CIE_SERIES, tiers=None, variants=(1, 2, 3), curriculum="cambridge"):
    tp = topics if isinstance(topics, dict) else {p: topics for p in papers}
    return code.lower(), {"code": code, "subject": subject, "level": level, "label": label, "papers": papers, "topics": tp,
                          "series": series, "tiers": tiers, "variants": variants, "curriculum": curriculum}


_IGT = {"1": "Core", "3": "Core", "2": "Core Extended", "4": "Core Extended", "5": "Practical", "6": "Practical"}
_MT = {"1": "Core", "3": "Core", "2": "Core Extended", "4": "Core Extended"}
QUALS = dict([
    _q("0580", "Mathematics", "IGCSE", "IGCSE Mathematics 0580", ["1", "2", "3", "4"], T_MATH, tiers=_MT),
    _q("0980", "Mathematics", "IGCSE", "IGCSE Mathematics (9-1) 0980", ["1", "2", "3", "4"], T_MATH, tiers=_MT),
    _q("0606", "Mathematics", "IGCSE", "IGCSE Additional Mathematics 0606", ["1", "2"], T_ADD),
    _q("0625", "Physics", "IGCSE", "IGCSE Physics 0625", ["1", "2", "3", "4", "5", "6"], T_PHY, tiers=_IGT),
    _q("0972", "Physics", "IGCSE", "IGCSE Physics (9-1) 0972", ["1", "2", "3", "4", "5", "6"], T_PHY, tiers=_IGT),
    _q("0620", "Chemistry", "IGCSE", "IGCSE Chemistry 0620", ["1", "2", "3", "4", "5", "6"], T_CHEM, tiers=_IGT),
    _q("0971", "Chemistry", "IGCSE", "IGCSE Chemistry (9-1) 0971", ["1", "2", "3", "4", "5", "6"], T_CHEM, tiers=_IGT),
    _q("0653", "Combined Science", "IGCSE", "IGCSE Combined Science 0653", ["1", "2", "3", "4", "5", "6"], T_SCI, tiers=_IGT),
    _q("0654", "Co-ordinated Sciences", "IGCSE", "IGCSE Co-ordinated Sciences 0654", ["1", "2", "3", "4", "5", "6"], T_SCI, tiers=_IGT),
    _q("4024", "Mathematics", "O Level", "O Level Mathematics D 4024", ["1", "2"], T_MATH),
    _q("4037", "Mathematics", "O Level", "O Level Additional Mathematics 4037", ["1", "2"], T_ADD),
    _q("9709", "Mathematics", "AS & A Level", "AS & A Level Mathematics 9709", ["1", "2", "3", "4", "5", "6"],
       {"1": P1_9709, "2": P3_9709, "3": P3_9709, "4": MECH, "5": PS1, "6": PS2}),
    _q("9231", "Further Mathematics", "AS & A Level", "AS & A Level Further Mathematics 9231", ["1", "2", "3", "4"], T_9231),
    _q("9702", "Physics", "AS & A Level", "AS & A Level Physics 9702", ["1", "2", "3", "4", "5"], T_9702),
    _q("9701", "Chemistry", "AS & A Level", "AS & A Level Chemistry 9701", ["1", "2", "3", "4", "5"], T_9701),
    _q("1112", "Mathematics", "Lower Secondary Checkpoint", "Lower Secondary Checkpoint Mathematics 1112", ["1", "2"], T_CP_MATH, series=CP_SERIES, variants=(1,)),
    _q("1113", "Science", "Lower Secondary Checkpoint", "Lower Secondary Checkpoint Science 1113", ["1", "2"], T_CP_SCI, series=CP_SERIES, variants=(1,)),
    *[_q(f"IB-{c}-{lv}", s, "IB Diploma", f"IB {name} {lv}", ["1", "2", "3"], t, series=IB_SESSIONS, variants=(0, 1, 2), curriculum="ib")
      for c, s, name, t in [("MAA", "Mathematics", "Mathematics: Analysis & Approaches", T_IB_MATH),
                            ("MAI", "Mathematics", "Mathematics: Applications & Interpretation", T_IB_MATH),
                            ("PHY", "Physics", "Physics", T_IB_PHY), ("CHE", "Chemistry", "Chemistry", T_IB_CHEM)] for lv in ("SL", "HL")],
    _q("NBT-AQL", "Academic & Quantitative Literacy", "NBT", "NBT Academic & Quantitative Literacy (AQL)", ["1"],
       ["Academic Literacy", "Quantitative Literacy"], series={"": "Tests"}, variants=(1,), curriculum="nbt"),
    _q("NBT-MAT", "Mathematics", "NBT", "NBT Mathematics (MAT)", ["1"],
       ["Algebraic Processes", "Functions & Graphs", "Number Sense", "Trigonometry", "Spatial Perception", "Data Handling & Probability", "Calculus"],
       series={"": "Tests"}, variants=(1,), curriculum="nbt"),
])
ROOT_FOLDERS = {"cambridge": "Cambridge Past Papers", "ib": "IB Diploma Past Papers", "nbt": "NBT Past Papers"}
CATALOGUE_FOLDERS = {"cambridge": "Cambridge", "ib": "IB", "nbt": "NBT"}
YEARS = range(2015, 2028)


def qual_for(meta) -> Optional[dict]:
    code = (getattr(meta, "qualification", "") or "").strip().lower()
    return QUALS.get(code) if getattr(meta, "curriculum", "") in ROOT_FOLDERS else None


def file_name(q: dict) -> str:
    return f"{'Cambridge ' if q['curriculum'] == 'cambridge' else ''}{q['label']} Catalogue.xlsx".replace(":", "")


def qual_folder(q: dict, paper: str) -> str:
    """Matches the existing Drive names, e.g. 'IGCSE Core Extended (0580)'."""
    tier = (q["tiers"] or {}).get(paper)
    return f"{q['level']}{' ' + tier if tier else ''} ({q['code']})"


def series_name(q: dict, session: str) -> str:
    return q["series"].get(session) or next(iter(q["series"].values()))


def variant_of(q: dict, meta) -> int:
    v = str(getattr(meta, "variant", "") or "").strip()
    return int(v) if v.isdigit() else q["variants"][0]


def paper_path(q: dict, meta, parent: List[str]) -> List[str]:
    """Folder holding Question Paper / Memo / Addendum / Errata / Questions for one paper."""
    p, v, year = meta.paper or q["papers"][0], variant_of(q, meta), meta.year or "Unknown Year"
    if q["curriculum"] == "nbt":
        return parent + [ROOT_FOLDERS["nbt"], q["label"], year]
    if q["curriculum"] == "ib":
        return parent + [ROOT_FOLDERS["ib"], year, q["subject"], q["label"].removeprefix("IB ").replace(":", ""), series_name(q, meta.session), f"TZ{v}", f"Paper_{p}"]
    return parent + [ROOT_FOLDERS["cambridge"], year, q["subject"], qual_folder(q, p), series_name(q, meta.session), f"Paper_{p}", f"Varient_{v}"]


def catalogue_path(q: dict, parent: List[str]) -> List[str]:
    return parent + ["Catalogues", CATALOGUE_FOLDERS[q["curriculum"]], q["subject"]]


def skeleton_paths(q: dict, years, parent: List[str]) -> List[List[str]]:
    from models import JobMeta
    out = []
    for y in years:
        for sess in q["series"]:
            for p in q["papers"]:
                for v in q["variants"]:
                    base = paper_path(q, JobMeta(year=str(y), session=sess, paper=p, variant=str(v)), parent)
                    out += [base + [d] for d in ("Question Paper", "Memo", "Addendum", "Errata", "Questions")]
    return out
