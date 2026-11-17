param(
    [Parameter(Mandatory = $true)]
    [ValidatePattern('^(10\.|192\.168\.|172\.(1[6-9]|2[0-9]|3[01])\.)')]
    [string]$LanSubnet
)

$ruleName = 'University Research Radar - LAN only'
$existingRule = Get-NetFirewallRule -DisplayName $ruleName -ErrorAction SilentlyContinue

if ($existingRule) {
    Set-NetFirewallRule -DisplayName $ruleName -Enabled True -Profile Private -Action Allow
    $existingRule | Get-NetFirewallAddressFilter | Set-NetFirewallAddressFilter -RemoteAddress $LanSubnet
    $existingRule | Get-NetFirewallPortFilter | Set-NetFirewallPortFilter -Protocol TCP -LocalPort 8501
} else {
    New-NetFirewallRule `
        -DisplayName $ruleName `
        -Direction Inbound `
        -Action Allow `
        -Protocol TCP `
        -LocalPort 8501 `
        -RemoteAddress $LanSubnet `
        -Profile Private
}

Get-NetFirewallRule -DisplayName $ruleName |
    Get-NetFirewallAddressFilter |
    Select-Object Name, RemoteAddress
