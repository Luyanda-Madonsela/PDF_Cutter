"""Canonical CAPS topic columns per (catalogue key, paper). IEB papers in these subjects examine the CAPS content, so they share the lists."""

_TRIG4 = ["Trigonometry - Identities & Reduction Formulae", "Trigonometry - General Solution & Equations",
          "Trigonometry - Problems in 2D & 3D", "Trigonometry - Trigonometric Graphs"]
_CALC4 = ["Differential Calculus - First Principles", "Differential Calculus - Rules of Differentiation",
          "Differential Calculus - Cubic Functions", "Differential Calculus - Optimisation & Rates of Change"]
_TRIG10 = ["Trigonometry - Ratios & Special Angles", "Trigonometry - Equations", "Trigonometry - Problems in 2D",
           "Trigonometry - Trigonometric Graphs"]
_TM_TRIG11 = ["Trigonometry - Reduction Formulae & Equations", "Trigonometry - Problems in 2D", "Trigonometry - Trigonometric Graphs"]
_TM_GEO = ["Analytical Geometry", "Euclidean Geometry", "Mensuration", "Circles, Angles & Angular Movement"]
_ML = ["Finance", "Measurement", "Maps, Plans & Other Representations", "Data Handling", "Probability",
       "Numbers & Calculations with Numbers", "Patterns, Relationships & Representations"]

CANON = {
    "gr12-maths": {
        "1": ["Algebra, Equations & Inequalities", "Number Patterns, Sequences & Series", "Finance, Growth & Decay",
              "Probability", "Functions & Graphs"] + _CALC4,
        "2": ["Statistics", "Analytical Geometry", "Euclidean Geometry"] + _TRIG4},
    "gr11-maths": {
        "1": ["Exponents & Surds", "Algebra, Equations & Inequalities", "Number Patterns", "Finance, Growth & Decay",
              "Probability", "Functions & Graphs"],
        "2": ["Statistics", "Analytical Geometry", "Euclidean Geometry", "Measurement"] + _TRIG4},
    "gr10-maths": {
        "1": ["Algebraic Expressions", "Exponents", "Number Patterns", "Equations & Inequalities", "Functions & Graphs",
              "Finance, Growth & Decay", "Probability"],
        "2": ["Statistics", "Analytical Geometry", "Euclidean Geometry", "Measurement"] + _TRIG10},
    "gr12-maths-lit": {"1": _ML, "2": _ML},
    "gr11-maths-lit": {"1": _ML, "2": _ML},
    "gr10-maths-lit": {"1": _ML, "2": _ML},
    "gr12-physical-sciences": {
        "1": ["Newton's Laws & Application of Newton's Laws", "Momentum & Impulse", "Vertical Projectile Motion in One Dimension",
              "Work, Energy & Power", "Doppler Effect", "Electrostatics", "Electric Circuits", "Electrodynamics",
              "Optical Phenomena & Properties of Materials"],
        "2": ["Organic Molecules", "Rate & Extent of Reaction", "Chemical Equilibrium", "Acids & Bases",
              "Electrochemical Reactions", "Chemical Industry (Fertilisers)"]},
    "gr11-physical-sciences": {
        "1": ["Vectors in Two Dimensions", "Newton's Laws & Application of Newton's Laws", "Electrostatics",
              "Electromagnetism", "Electric Circuits", "Geometrical Optics", "2D & 3D Wavefronts"],
        "2": ["Atomic Combinations (Molecular Structure)", "Intermolecular Forces", "Ideal Gases & Thermal Properties",
              "Quantitative Aspects of Chemical Change", "Energy & Chemical Change",
              "Types of Reactions (Acid-Base & Redox)", "The Lithosphere"]},
    "gr10-physical-sciences": {
        "1": ["Vectors & Scalars", "Motion in One Dimension", "Energy", "Waves, Sound & Light", "Magnetism",
              "Electrostatics", "Electric Circuits"],
        "2": ["Matter & Classification", "States of Matter & Kinetic Molecular Theory", "Atomic Structure & Periodic Table",
              "Chemical Bonding", "Physical & Chemical Change", "Representing Chemical Change",
              "Reactions in Aqueous Solution", "Quantitative Aspects of Chemical Change", "The Hydrosphere"]},
    "gr12-technical-maths": {
        "1": ["Algebra, Equations, Inequalities & Complex Numbers", "Functions & Graphs", "Finance, Growth & Decay"]
             + _CALC4 + ["Integral Calculus"],
        "2": _TM_GEO + _TRIG4},
    "gr11-technical-maths": {
        "1": ["Exponents & Logarithms", "Algebra, Equations & Inequalities", "Functions & Graphs", "Finance, Growth & Decay"],
        "2": _TM_GEO + _TM_TRIG11},
    "gr10-technical-maths": {
        "1": ["Number Systems", "Exponents & Logarithms", "Algebra, Equations & Inequalities", "Functions & Graphs",
              "Finance, Growth & Decay"],
        "2": _TM_GEO + ["Trigonometry - Ratios & Special Angles", "Trigonometry - Problems in 2D", "Trigonometry - Trigonometric Graphs"]},
}

# old column / stored topic name -> canonical name (per catalogue; "*" applies to all)
RENAMES = {
    "*": {"Maps & Plans": "Maps, Plans & Other Representations", "Mixed": "Numbers & Calculations with Numbers",
          "Patterns, relationships & representations": "Patterns, Relationships & Representations"},
    "gr10-maths": {"Number System": "Algebraic Expressions", "Trigonometry": "Trigonometry - Ratios & Special Angles",
                   "Trigonometry - Identities & Reduction Formulae": "Trigonometry - Ratios & Special Angles",
                   "Trigonometry - General Solution & Equations": "Trigonometry - Equations",
                   "Trigonometry - Problems in 2D & 3D": "Trigonometry - Problems in 2D"},
    "gr10-physical-sciences": {"Transverse Pulses & Waves": "Waves, Sound & Light", "Electricity & Magnetism": "Electric Circuits"},
    "gr12-physical-sciences": {"Chemical Bonding": "Organic Molecules"},
    "gr12-technical-maths": {"Algebra, Equations & Inequalities": "Algebra, Equations, Inequalities & Complex Numbers",
                             "Measurement": "Circles, Angles & Angular Movement"},
    "gr11-technical-maths": {"Measurement": "Circles, Angles & Angular Movement",
                             "Trigonometry - Identities & Reduction Formulae": "Trigonometry - Reduction Formulae & Equations",
                             "Trigonometry - General Solution & Equations": "Trigonometry - Reduction Formulae & Equations",
                             "Trigonometry - Problems in 2D & 3D": "Trigonometry - Problems in 2D"},
    "gr10-technical-maths": {"Measurement": "Circles, Angles & Angular Movement",
                             "Algebra, Equations & Inequalities": "Algebra, Equations & Inequalities",
                             "Trigonometry - Identities & Reduction Formulae": "Trigonometry - Ratios & Special Angles",
                             "Trigonometry - General Solution & Equations": "Trigonometry - Ratios & Special Angles",
                             "Trigonometry - Problems in 2D & 3D": "Trigonometry - Problems in 2D"},
    "gr12-maths": {"Patterns": "Number Patterns, Sequences & Series", "Number Patterns": "Number Patterns, Sequences & Series"},
}


def rename(key: str, name: str) -> str:
    return RENAMES.get(key, {}).get(name) or RENAMES["*"].get(name) or name
