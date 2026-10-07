param([Parameter(Mandatory=$true)][string]$DocumentPath, [Parameter(Mandatory=$true)][string]$PdfPath)
$ErrorActionPreference = 'Stop'
$word = $null
$document = $null
try {
    $word = New-Object -ComObject Word.Application
    $word.Visible = $false
    $word.DisplayAlerts = 0
    $document = $word.Documents.Open($DocumentPath, $false, $true)
    $document.Repaginate()
    $document.ExportAsFixedFormat($PdfPath, 17)
    Write-Output "Pages: $($document.ComputeStatistics(2))"
} finally {
    if ($null -ne $document) { $document.Close(0) }
    if ($null -ne $word) { $word.Quit() }
}
