function Get-Discount {
    param([double]$Amount)
    # Regras atuais (docs/CHANGELOG.md 2.0, substitui SPEC 1.0):
    #   >= 100       : 15%
    #   50 a 99,99   : 5%
    #   < 50         : sem desconto
    if ($Amount -ge 100) { return $Amount * 0.15 }
    if ($Amount -ge 50) { return $Amount * 0.05 }
    return 0
}
