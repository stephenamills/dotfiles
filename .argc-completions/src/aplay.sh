_patch_help() { 
    $@ --help | sed '/Recognized sample formats are:/,$ d'
}

_patch_table() { 
    _patch_table_edit_options \
        '--device;[`_choice_card`]' \
        '--file-type;[voc|wav|raw|au]' \
        '--format;[`_choice_format`]' \
        '--vumeter;[mono|stereo]' \

}

_choice_card() {
    aplay -l | grep '^card [0-9]\+' | sed 's/card \([0-9]\+\): \(.\+\) \[.*\].*/\1\t\2/'
}

_choice_format() {
    cat <<-'EOF'
S8
A_LAW
DSD_U16_BE
DSD_U16_LE
DSD_U32_BE
DSD_U32_LE
DSD_U8
FLOAT64_BE
FLOAT64_LE
FLOAT_BE
FLOAT_LE
G723_24
G723_24_1B
G723_40
G723_40_1B
GSM
IEC958_SUBFRAME_BE
IEC958_SUBFRAME_LE
IMA_ADPCM
MPEG
MU_LAW
S16_BE
S16_LE
S18_3BE
S18_3LE
S20_3BE
S20_3LE
S20_BE
S20_LE
S24_3BE
S24_3LE
S24_BE
S24_LE
S32_BE
S32_LE
SPECIAL
U16_BE
U16_LE
U18_3BE
U18_3LE
U20_3BE
U20_3LE
U20_BE
U20_LE
U24_3BE
U24_3LE
U24_BE
U24_LE
U32_BE
U32_LE
U8
EOF
}