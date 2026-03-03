#!/bin/bash
# WM8960 ALSA mixer settings for Cortex voice capture on Whisplay HAT.
#
# Tuned for speech capture with the onboard MEMS mic via ALSA default device:
#   - Capture gain: PGA=55/63, Boost=+20dB (headroom for loud speech)
#   - ALC disabled (compresses too aggressively on WM8960)
#   - High Pass Filter: removes DC offset and low-freq rumble
#   - Noise Gate: reduces background noise between utterances
#
# Run once after boot, or save with: sudo alsactl store
# Usage: bash scripts/setup-mixer.sh

set -e

CARD=0

echo "Configuring WM8960 mixer on card $CARD for voice capture..."

# --- Capture path ---
# PGA gain: 55/63 (~+22.6dB, reduced from max to avoid clipping with default device)
# With the ALSA default device (plug→dsnoop), signal is ~5x stronger than raw hw:0,0.
amixer -c $CARD cset name='Capture Volume' 55,55 > /dev/null
amixer -c $CARD cset name='Capture Switch' on,on > /dev/null

# Input boost: 2 = +20dB via LINPUT1
amixer -c $CARD cset name='Left Input Boost Mixer LINPUT1 Volume' 2 > /dev/null
amixer -c $CARD cset name='Right Input Boost Mixer RINPUT1 Volume' 2 > /dev/null
amixer -c $CARD cset name='Left Boost Mixer LINPUT1 Switch' on > /dev/null
amixer -c $CARD cset name='Right Boost Mixer RINPUT1 Switch' on > /dev/null

# ADC settings
amixer -c $CARD cset name='ADC PCM Capture Volume' 195,195 > /dev/null
amixer -c $CARD cset name='ADC High Pass Filter Switch' on > /dev/null

# ALC (Automatic Level Control) — disabled
# ALC compresses speech signal too aggressively on WM8960.
# With Capture=50 + Boost=2 + default ALSA device, peak speech ~40-70% of max,
# leaving good headroom without clipping.
amixer -c $CARD cset name='ALC Function' 0 > /dev/null  # Off

# Noise gate
amixer -c $CARD cset name='Noise Gate Switch' on > /dev/null
amixer -c $CARD cset name='Noise Gate Threshold' 3 > /dev/null

# --- Playback path ---
amixer -c $CARD cset name='Speaker Playback Volume' 121,121 > /dev/null
amixer -c $CARD cset name='Speaker DC Volume' 4 > /dev/null
amixer -c $CARD cset name='Speaker AC Volume' 4 > /dev/null
amixer -c $CARD cset name='Playback Volume' 255,255 > /dev/null
amixer -c $CARD cset name='Left Output Mixer PCM Playback Switch' on > /dev/null
amixer -c $CARD cset name='Right Output Mixer PCM Playback Switch' on > /dev/null

echo "WM8960 mixer configured for Cortex voice capture."
