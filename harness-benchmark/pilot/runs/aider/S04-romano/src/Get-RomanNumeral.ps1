function Get-RomanNumeral {
    param([int]$Number)

    if ($Number -lt 1 -or $Number -gt 3999) {
        throw "O número deve estar entre 1 e 3999. Valor recebido: $Number"
    }

    $tabela = @(
        @{ Valor = 1000; Simbolo = 'M'  }
        @{ Valor = 900;  Simbolo = 'CM' }
        @{ Valor = 500;  Simbolo = 'D'  }
        @{ Valor = 400;  Simbolo = 'CD' }
        @{ Valor = 100;  Simbolo = 'C'  }
        @{ Valor = 90;   Simbolo = 'XC' }
        @{ Valor = 50;   Simbolo = 'L'  }
        @{ Valor = 40;   Simbolo = 'XL' }
        @{ Valor = 10;   Simbolo = 'X'  }
        @{ Valor = 9;    Simbolo = 'IX' }
        @{ Valor = 5;    Simbolo = 'V'  }
        @{ Valor = 4;    Simbolo = 'IV' }
        @{ Valor = 1;    Simbolo = 'I'  }
    )

    $resultado = ''
    $restante = $Number
    foreach ($item in $tabela) {
        while ($restante -ge $item.Valor) {
            $resultado += $item.Simbolo
            $restante -= $item.Valor
        }
    }

    return $resultado
}
