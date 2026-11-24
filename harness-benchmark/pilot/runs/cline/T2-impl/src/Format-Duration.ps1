function Format-Duration {
    param([int]$Seconds)
    $horas = [int][math]::Floor($Seconds / 3600)
    $minutos = [int][math]::Floor(($Seconds % 3600) / 60)
    $segundos = [int]($Seconds % 60)
    return ("{0}h {1:D2}m {2:D2}s" -f $horas, $minutos, $segundos)
}
