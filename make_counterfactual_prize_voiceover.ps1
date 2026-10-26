# Local-only English speech for an owner-approved, silent 180s Counterfactual Lab capture.
# Usage: pwsh -NoProfile -File .\make_counterfactual_prize_voiceover.ps1 -Session 2026-10-23T20-14-02-315Z-record
# No provider API, password, microphone, desktop capture or new browser session.
[CmdletBinding()]
param(
  [Parameter(Mandatory=$true)]
  [ValidatePattern('^\d{4}-\d{2}-\d{2}T\d{2}-\d{2}-\d{2}-\d{3}Z-record$')]
  [string]$Session
)
$ErrorActionPreference = 'Stop'
$root = $PSScriptRoot
$python = Join-Path $root 'mix_counterfactual_prize_narration.py'
& py -3 $python --verify-input --session $Session
if ($LASTEXITCODE -ne 0) { throw 'LOCAL_VIDEO_INPUT_NOT_VERIFIED' }

Add-Type -AssemblyName System.Speech
$out = Join-Path $root ('acceptance\logs\prize-video-local\' + $Session)
$voiceDir = Join-Path $out 'voiceover-180s'
$completed = Join-Path $out 'EvidenceTrail_Counterfactual_DEMO_NARRATED_REVIEW.mp4'
if (Test-Path -LiteralPath $voiceDir) { throw 'VOICE_DIRECTORY_EXISTS_REFUSING_OVERWRITE' }
if (Test-Path -LiteralPath $completed) { throw 'NARRATED_VIDEO_EXISTS_REFUSING_OVERWRITE' }
New-Item -ItemType Directory -Path $voiceDir -ErrorAction Stop | Out-Null

# Caption/timeline alignment: 0,13,40,59,91,126,152,169,180 sec.
# Interpret all reported WARNs as SIMULATED and all site capacity as FICTIONAL.
$lines = @(
  'This is EvidenceTrail, an agent designed to explain why evidence supports a decision, and when it does not. The Yagi case is an offline historical research simulation.',
  'At sixteen thirty, the government report has an observation time of fifteen hundred, but its displayed publication dateline is sixteen thirty seven. The agent does not let the earlier observation time become proof the article was already public. It excludes the later district report and abstains. This is the first trust boundary.',
  'The evidence timeline is not decoration. It is checked before the deterministic decision. When a required district-named source has not yet passed the selected source-time policy, the answer is insufficient evidence, not a confidently worded guess.',
  'Advance the replay to sixteen forty five. A district government bulletin can now enter the reported-dateline evidence set. Combined with explicitly fictional internal capacity, the research rule computes a simulated warning. This is not an authenticated historic prediction, a current evacuation recommendation, or a validated population estimate. The agent states exactly which source changed eligibility.',
  'Now remove evidence to test the explanation. The counterfactual lab finds a minimum set of two inputs: the dated district government report and fictional scenario capacity. Remove the district report, and the rule abstains. Put it back and remove capacity: the rule abstains again. Those two witnesses are pivotal under the current sample rules; this does not prove real-world causation.',
  'Switch to strict as-of twenty twenty four. Here the agent demands independent proof that the original article was already publicly available at the decision moment. A later archive capture does not establish that fact. The strict result therefore remains insufficient evidence, even though the reported-dateline replay warned.',
  'This proof panel separates independently exercised local integrations from model inference. We verified local Zetaris data retrieval and cross-process memory using the official H mem reference. The browser demonstration itself is keyless, offline and reproducible.',
  'The NVIDIA model route has no accepted completion. Sponsor eligibility and real-world disaster accuracy are not verified. EvidenceTrail makes its limits visible.'
)
if ($lines.Count -ne 8) { throw 'VOICE_SCENE_COUNT_INVALID' }
$synth = [System.Speech.Synthesis.SpeechSynthesizer]::new()
try {
  $voices = @($synth.GetInstalledVoices() | Where-Object {
    $_.Enabled -and $_.VoiceInfo.Culture.Name -like 'en-*'
  } | ForEach-Object { $_.VoiceInfo.Name })
  if ($voices.Count -eq 0) { throw 'ENGLISH_WINDOWS_TTS_VOICE_MISSING' }
  $choice = if ($voices -contains 'Microsoft Zira Desktop') { 'Microsoft Zira Desktop' } else { $voices[0] }
  $synth.SelectVoice($choice)
  $synth.Rate = 2
  $synth.Volume = 90
  for ($i=0; $i -lt $lines.Count; $i++) {
    $path = Join-Path $voiceDir ('voice-{0:D2}.wav' -f $i)
    $synth.SetOutputToWaveFile($path)
    try { $synth.Speak($lines[$i]) }
    finally { $synth.SetOutputToNull() }
    Write-Output ('LOCAL_TTS_SCENE_{0}_BYTES={1}' -f $i,(Get-Item -LiteralPath $path).Length)
  }
} finally { $synth.Dispose() }

& py -3 $python --mix --session $Session
if ($LASTEXITCODE -ne 0) { throw 'OFFLINE_NARRATION_MIX_OR_DECODE_FAILED' }
