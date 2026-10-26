# Offline, local-only English narration for the EvidenceTrail judge video.
# Requires PowerShell 7, .NET System.Speech and an installed English Windows voice.
# No cloud accounts, microphone, uploads or user-profile browser access.
# Source video is generated separately via: node record_judge_video.mjs --record
param([switch]$OnlyVoices)
$ErrorActionPreference='Stop'
Add-Type -AssemblyName System.Speech
$root=$PSScriptRoot
$out=Join-Path $root 'acceptance\logs\judge-video-20261023'
$wav=Join-Path $out 'voiceover-draft'
New-Item -ItemType Directory -Path $wav -Force | Out-Null
$synth=[System.Speech.Synthesis.SpeechSynthesizer]::new()
try {
    $candidates=@($synth.GetInstalledVoices() | Where-Object {
        $_.VoiceInfo.Culture.Name -eq 'en-US'
    } | ForEach-Object {$_.VoiceInfo.Name})
    if($candidates.Count -eq 0){throw 'NO_EN_US_WINDOWS_SPEECH_VOICE'}
    $voice=if($candidates -contains 'Microsoft Zira Desktop'){'Microsoft Zira Desktop'}else{$candidates[0]}
    $synth.SelectVoice($voice)
    $synth.Rate=1
    $synth.Volume=90
    $lines=@(
      'A safety critical assistant must explain when evidence becomes admissible. This is an offline research replay of the 2024 Yagi disaster.',
      'At sixteen thirty, a government article mentions river gauges measured at fifteen hundred. But its displayed publication dateline is sixteen thirty seven.',
      'The temporal firewall rejects that article before deciding, and records the exclusion. The agent abstains instead of guessing.',
      'At sixteen forty five, the district report can enter the evidence set. The warning is simulated, using fictional coordinator capacity.',
      'Compare computes precisely which source became eligible. The clock alone does not cause a warning. This new district citation explains why.',
      'Strict mode refuses the claim. Without immutable original archive bytes, we cannot prove what was public in twenty twenty four.',
      'The audit displays excluded sources and remaining unknowns. Reported datelines are not authenticated first publication times.',
      'Two real local Zetaris queries succeeded, and official Meterless H mem recalled prior context. Nightshift inference and organizer acceptance remain unverified.'
    )
    for($i=0;$i -lt $lines.Count;$i++){
        $file=Join-Path $wav ('voice-{0:D2}.wav' -f $i)
        $synth.SetOutputToWaveFile($file)
        $synth.Speak($lines[$i])
        $synth.SetOutputToNull()
        Write-Output ('GENERATED_VOICE_'+$i+' BYTES='+(Get-Item $file).Length)
    }
}finally{
    $synth.Dispose()
}
if(!$OnlyVoices){
    & py -3 (Join-Path $root 'mix_judge_narration.py')
    if($LASTEXITCODE -ne 0){throw 'LOCAL_VOICEOVER_MIX_FAILED'}
}
