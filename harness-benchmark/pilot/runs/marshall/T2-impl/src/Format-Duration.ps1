function Format-Duration {
    param([int]$Seconds)
    $h = [int][math]::Floor($Seconds / 3600)
    $m = [int][math]::Floor(($Seconds % 3600) / 60)
    $s = $Seconds % 60
    return ("{0}h {1:00}m {2:00}s" -f $h, $m, $s)
}
