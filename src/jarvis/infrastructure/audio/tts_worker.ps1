$ErrorActionPreference='Stop'
Add-Type -AssemblyName System.Speech
$utf8=New-Object Text.UTF8Encoding($false)
$reader=New-Object IO.StreamReader([Console]::OpenStandardInput(),$utf8)
$writer=New-Object IO.StreamWriter([Console]::OpenStandardOutput(),$utf8)
$writer.AutoFlush=$true
$synth=New-Object System.Speech.Synthesis.SpeechSynthesizer
$format=New-Object System.Speech.AudioFormat.SpeechAudioFormatInfo(24000,[System.Speech.AudioFormat.AudioBitsPerSample]::Sixteen,[System.Speech.AudioFormat.AudioChannel]::Mono)
$voices=@($synth.GetInstalledVoices() | Where-Object {$_.Enabled -and $_.VoiceInfo.Culture.Name -eq 'zh-CN'})
if($voices.Count -gt 0){$synth.SelectVoice($voices[0].VoiceInfo.Name)}
$writer.WriteLine('{"ready":true}')
try {
 while($null -ne ($line=$reader.ReadLine())) {
  $job=ConvertFrom-Json $line
  if($job.close){break}
  try {
   $synth.SetOutputToWaveFile([string]$job.output,$format)
   $synth.Speak([string]$job.text)
   $synth.SetOutputToNull()
   $writer.WriteLine('{"ok":true}')
  } catch {
   $synth.SetOutputToNull()
   $writer.WriteLine('{"ok":false}')
  }
 }
} finally {$synth.Dispose();$reader.Dispose();$writer.Dispose()}
