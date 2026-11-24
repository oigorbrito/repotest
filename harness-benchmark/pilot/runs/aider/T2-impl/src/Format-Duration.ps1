function Format-Duration {
    param([int]$Seconds)
    $horas = [math]::Floor($Seconds / 3600)
    $minutos = [math]::Floor(($Seconds % 3600) / 60)
    $segundos = $Seconds % 60
    return "{0}h {1:00}m {2:00}s" -f $horas, $minutos, $segundos
}
