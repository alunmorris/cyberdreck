# firmware/boards/CRACK_S2/mpconfigboard.cmake
set(IDF_TARGET esp32s2)
set(SDKCONFIG_DEFAULTS
    boards/sdkconfig.base
    boards/sdkconfig.240mhz
    boards/sdkconfig.spiram_sx
    ${MICROPY_BOARD_DIR}/sdkconfig.board
)
