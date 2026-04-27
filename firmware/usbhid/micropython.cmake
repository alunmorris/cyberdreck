add_library(usermod_usbhid INTERFACE)
target_sources(usermod_usbhid INTERFACE
    ${CMAKE_CURRENT_LIST_DIR}/usbhid.c
)
target_include_directories(usermod_usbhid INTERFACE
    ${CMAKE_CURRENT_LIST_DIR}
)
target_link_libraries(usermod INTERFACE usermod_usbhid)
