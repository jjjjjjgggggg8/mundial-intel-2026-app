TEAM_ALIASES = {
    # América del Norte
    "USA":                          "United States",
    "US":                           "United States",
    # Asia
    "Korea Republic":               "South Korea",
    "Korea DPR":                    "North Korea",
    "IR Iran":                      "Iran",
    # Europa
    "Czech Republic":               "Czechia",
    "Türkiye":                      "Turkey",
    "FYR Macedonia":                "North Macedonia",
    "Republic of Ireland":          "Ireland",
    "Bosnia-Herzegovina":           "Bosnia and Herzegovina",
    # África
    "Côte d'Ivoire":                "Ivory Coast",
    "Congo DR":                     "DR Congo",
    "Cape Verde Islands":           "Cape Verde",
    # Variantes históricas
    "West Germany":                 "Germany",
    "Soviet Union":                 "Russia",
    "Yugoslavia":                   "Serbia",
    "Czechoslovakia":               "Czechia",
    # Unicode / tildes
    "São Tomé and Príncipe":        "Sao Tome and Principe",
    # CSV de Kaggle
    "Kyrgyz Republic":              "Kyrgyzstan",
    "Macau":                        "Macao",
    "Chinese Taipei":               "Taiwan",
}


def normalize_team_name(name: str) -> str:
    if name is None:
        return "Unknown"
    stripped = name.strip()
    return TEAM_ALIASES.get(stripped, stripped)
