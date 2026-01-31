# TODO

## 🐛 Bugs

### High Priority


### Medium Priority
- [ ] Keyboard character select and Keyboard mode bottom menu doesn't show on web UI (only OLED display)

### Low Priority
- [ ] When text is scrolling (for eg in the 'choose image' screen, depending on the length the text is changes the speed of the scroll. I want all iteams to scroll at the same speed.
- [x] Screensaver screen shows the "select gif" menu option when the mode is set to Random, it should only show the "select gif" option when the "mode" is set to "selected". (Fixed 2026-01-29)
- [ ] In web UI, when you hover mouse over OLED preview image show a fullscreen glyph and when you click the glyph it shows the OLED preview fullscreen (users can still navigate with keyboard).

## 🚀 Features

### Core Functionality
- [x] Allow users to create a new Repo Drive using the menu system (creates flag file on drive)
- [ ] Implement checkbox UI for partition selection during backup/restore (image_actions.py:676)

### User Experience
- [ ] Add operation history/audit log
- [ ] Implement save/resume for interrupted operations
- [ ] Add SMART status monitoring for drive health

### Advanced
- [x] **Image Transfer between Pis** - Transfer disk images between devices:
  - USB-to-USB (plugging destination drive into source Pi)
  - Ethernet Direct (mDNS discovery + HTTP transfer)
  - WiFi Direct (P2P wireless without router)
- [x] **Bluetooth PAN** - Bluetooth tethering for web UI access without WiFi:
  - Pi acts as Bluetooth NAP (Network Access Point)
  - QR code pairing display
  - Internet sharing via phone tethering
  - Trusted devices with auto-reconnect
- [ ] Network share mounting (SMB/NFS) for image repositories
- [ ] Batch operation queue system
- [ ] Scheduled automated backups
- [ ] Parallel multi-drive cloning


## 🎨 Polish

- [ ] Mobile-responsive web UI improvements
- [ ] Improve error recovery flows
- [x] Add comprehensive operation logging (✅ Complete - all operations now visible in Web UI)
- [ ] Web UI theme consistency with OLED display

## 📝 Documentation

- [ ] Add troubleshooting guide for common issues
- [ ] Document Clonezilla integration architecture
- [ ] Create user guide for web UI features

---

**Legend**: 🐛 Bugs | 🚀 Features | 🎨 Polish | 📝 Documentation
