from pathlib import Path
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, PageBreak, Table, TableStyle, Image, KeepTogether

ROOT = Path(__file__).resolve().parents[1]
RELEASE_VERSION = (ROOT / "VERSION").read_text().strip()
OUT = ROOT / "docs" / "publications" / f"N0JCG_Air_Band_Scanner_User_Guide_v{RELEASE_VERSION}.pdf"
LOGO = ROOT / "web" / "assets" / "N0JCG_Header_Dark_Approved.png"
MAIN = ROOT / "docs" / "screenshots-airband-main.png"
MENU = ROOT / "docs" / "screenshots-airband-menu.png"

NAVY = colors.HexColor("#0A1F44")
BLUE = colors.HexColor("#1565C0")
CYAN = colors.HexColor("#00B8D9")
SLATE = colors.HexColor("#2B3440")
MIST = colors.HexColor("#F4F7FA")
TEXT = colors.HexColor("#15202B")
MUTED = colors.HexColor("#6B7785")

styles = getSampleStyleSheet()
styles.add(ParagraphStyle(name="CoverTitle", parent=styles["Title"], fontName="Helvetica-Bold", fontSize=27, leading=32, textColor=NAVY, alignment=TA_CENTER, spaceAfter=10))
styles.add(ParagraphStyle(name="CoverSub", parent=styles["Normal"], fontName="Helvetica", fontSize=13, leading=18, textColor=SLATE, alignment=TA_CENTER, spaceAfter=18))
styles.add(ParagraphStyle(name="Kicker", parent=styles["Normal"], fontName="Helvetica-Bold", fontSize=9, leading=11, textColor=CYAN, alignment=TA_CENTER, spaceAfter=9))
styles.add(ParagraphStyle(name="H1N0", parent=styles["Heading1"], fontName="Helvetica-Bold", fontSize=18, leading=22, textColor=NAVY, spaceBefore=12, spaceAfter=7, borderPadding=4, borderColor=CYAN, borderWidth=0, borderBottomWidth=1))
styles.add(ParagraphStyle(name="H2N0", parent=styles["Heading2"], fontName="Helvetica-Bold", fontSize=13, leading=17, textColor=BLUE, spaceBefore=9, spaceAfter=5))
styles.add(ParagraphStyle(name="BodyN0", parent=styles["BodyText"], fontName="Helvetica", fontSize=9.7, leading=13.2, textColor=TEXT, spaceAfter=6))
styles.add(ParagraphStyle(name="SmallN0", parent=styles["BodyText"], fontName="Helvetica", fontSize=8.5, leading=11, textColor=MUTED, spaceAfter=4))
styles.add(ParagraphStyle(name="BulletN0", parent=styles["BodyText"], fontName="Helvetica", fontSize=9.5, leading=12.5, textColor=TEXT, leftIndent=14, firstLineIndent=-8, bulletIndent=3, spaceAfter=3))
styles.add(ParagraphStyle(name="CalloutN0", parent=styles["BodyText"], fontName="Helvetica-Bold", fontSize=9.5, leading=13, textColor=NAVY, backColor=colors.HexColor("#E8FAFD"), borderColor=CYAN, borderWidth=1, borderPadding=8, spaceBefore=7, spaceAfter=9))

def P(text, style="BodyN0"):
    return Paragraph(text, styles[style])

def bullets(items):
    return [P("• " + item, "BulletN0") for item in items]

def footer(canvas, doc):
    canvas.saveState()
    canvas.setStrokeColor(CYAN)
    canvas.setLineWidth(0.6)
    canvas.line(0.85*inch, 0.58*inch, 7.65*inch, 0.58*inch)
    canvas.setFillColor(MUTED)
    canvas.setFont("Helvetica", 8)
    canvas.drawString(0.85*inch, 0.38*inch, f"N0JCG Open Radio Platform  |  Air Band Scanner v{RELEASE_VERSION}")
    canvas.drawRightString(7.65*inch, 0.38*inch, f"Page {doc.page}")
    canvas.restoreState()

def metadata_table(rows):
    data = [[P(f"<b>{k}</b>", "SmallN0"), P(v, "BodyN0")] for k, v in rows]
    t = Table(data, colWidths=[1.55*inch, 5.2*inch], hAlign="LEFT")
    t.setStyle(TableStyle([("BACKGROUND", (0,0), (0,-1), MIST), ("BOX", (0,0), (-1,-1), 0.5, colors.HexColor("#D6DEE9")), ("INNERGRID", (0,0), (-1,-1), 0.25, colors.HexColor("#D6DEE9")), ("VALIGN", (0,0), (-1,-1), "TOP"), ("LEFTPADDING", (0,0), (-1,-1), 8), ("RIGHTPADDING", (0,0), (-1,-1), 8), ("TOPPADDING", (0,0), (-1,-1), 6), ("BOTTOMPADDING", (0,0), (-1,-1), 6)]))
    return t

story = []
banner = Table([[Image(str(LOGO), width=4.5*inch, height=0.86*inch)]], colWidths=[6.8*inch], rowHeights=[1.25*inch])
banner.setStyle(TableStyle([("BACKGROUND", (0,0), (-1,-1), NAVY), ("VALIGN", (0,0), (-1,-1), "MIDDLE"), ("ALIGN", (0,0), (-1,-1), "CENTER")]))
story += [banner, Spacer(1, 0.45*inch), P("OPERATOR HANDBOOK", "Kicker"), P("N0JCG Air Band Scanner", "CoverTitle"), P("Installation, registration, operation, and troubleshooting", "CoverSub"), Spacer(1, 0.1*inch), P("A receive-only civil Airband scanner for FFT-directed channel selection, airport-code lookup, and browser audio.", "CalloutN0"), metadata_table([("RELEASE", f"{RELEASE_VERSION} Preview"), ("RECEIVER", "RTL-SDR EEPROM serial 00000118"), ("BAND", "118.000–136.975 MHz civil Airband"), ("REGISTRATION", "n0jcg-air-band-scanner / N0JCG-ABS-"), ("AUDIENCE", "Operators and maintainers")]), PageBreak()]

story += [P("Contents", "H1N0"), P("Use this guide from initial hardware setup through daily operation and maintenance."), *bullets(["Product boundary and safety", "Hardware and installation", "Trial and registration", "Scanning, tuning, and browser audio", "Nearby FAA and airport-code workflows", "Channel controls and troubleshooting", "Audio/RF reference and acceptance checklist"]), P("Receiver ownership is serial-first. The application is bound to RTL-SDR serial 00000118; USB enumeration indexes are not permanent assignments.", "CalloutN0"), P("1. Product boundary and safety", "H1N0"), P("N0JCG Air Band Scanner is a standalone, receive-only civil Airband application. It does not transmit, key a radio, decode encrypted traffic, or share runtime ownership with N0JCG Scanner, N0JCG NOAA Weather Radio, or N0JCG Air Traffic Center."), *bullets(["Use an antenna and filter path appropriate for approximately 118–137 MHz.", "Do not interpret monitoring output as navigation, safety-of-flight, or dispatch guidance.", "Stop the service before changing hardware or assigning the RTL-SDR to another application."]), P("2. Hardware and installation", "H1N0"), P("Use a Raspberry Pi or compatible Linux host with rtl_power and rtl_fm installed. Connect the RTL-SDR programmed with EEPROM serial 00000118 and an appropriate Airband antenna."), P("On Raspberry Pi OS, copy the repository to the Pi and run <font name='Courier'>sudo ./deploy/install.sh</font>. The operator interface is served on port 8087. Run <font name='Courier'>./deploy/install.sh --check-only</font> before installation to distinguish missing tools from RF problems."), PageBreak()]

story += [P("3. Trial and registration", "H1N0"), P("An unregistered installation starts a five-minute trial when scanning or tuning first begins. The header displays the remaining time and the trial control is disabled while the timer runs. When the five minutes expire, the same control becomes <b>Restart Trial</b>; scanning and tuning controls remain disabled until the trial is restarted."), P("Open <b>Menu - Registration</b> and enter the license S/N and registered purchaser email. The registration identity is:", "BodyN0"), metadata_table([("PRODUCT", "N0JCG Air Band Scanner"), ("PRODUCT ID", "n0jcg-air-band-scanner"), ("LICENSE PREFIX", "N0JCG-ABS-")]), P("Select <b>Activate license</b>. Activation is sent through the application backend to the N0JCG licensing service. The signed license lease is cached locally for continued operation and refresh. After successful registration, the trial timer/status control is hidden from the header."), P("4. Main operator screen", "H1N0"), Image(str(MAIN), width=6.7*inch, height=2.55*inch), P("The main screen provides Full Airband and Nearby FAA scope selection, Start/Stop, Skip, compact squelch controls, current-channel Pause/Block/Clear controls, and direct Tune actions for nearby channels.", "SmallN0"), P("Press <b>Start</b> to begin scanning and browser audio. The button changes to <b>Stop</b> while active. <b>Skip</b> moves on from the current scanning channel. A direct Tune is a persistent manual lock and does not restart scanning when the seven-second silence timeout expires.", "BodyN0"), PageBreak()]

story += [P("5. Operator menu", "H1N0"), Image(str(MENU), width=6.7*inch, height=2.52*inch), P("The Menu contains Registration, receiver tuning, receiver location/radius, airport-code lookup, and FFT candidate tools. The Nearby FAA channel list remains on the main page.", "SmallN0"), P("6. Scanning and tuning", "H1N0"), *bullets(["Full Airband surveys 118.000–136.975 MHz across the loaded channel catalog.", "Nearby FAA scans only known FAA channels inside the saved receiver radius.", "The FFT scan scores candidates and tunes the strongest valid candidate above the configured activity/SNR gate.", "Airport lookup accepts codes such as KDEN and returns ATIS, tower, ground, approach, and UNICOM frequencies when present in the imported FAA catalog.", "Use a nearby channel's Tune button for direct listening. It starts audio and holds that channel until Stop or another explicit operator action."]), P("7. Audio and squelch", "H1N0"), P("The receiver uses AM demodulation and scheduled, finite WAV chunks containing 24 kHz mono PCM audio. Browser playback uses the system/browser volume path. Playback squelch is independent of the FFT activity threshold: 0 is open squelch; a positive value mutes audio below the selected RMS level."), P("When a scanning channel remains below squelch for seven seconds, the scanner releases it and resumes the selected scan scope. Direct manual Tune locks persist through this timeout."), PageBreak()]

story += [P("8. Pause, block, skip, and clear", "H1N0"), *bullets(["Pause 10 min temporarily removes the currently locked scanning frequency from FFT scanning, then makes it eligible again.", "Block removes the currently locked scanning frequency from scanning until Clear all is selected.", "Skip moves immediately to another candidate and applies the temporary skip behavior to the current scanning channel.", "Clear all clears all paused and blocked channel controls.", "These controls affect scanning only; a deliberate direct Tune remains a manual listening lock."]), P("9. Troubleshooting", "H1N0"), *bullets(["No candidates: verify antenna/filter connections, local activity, gain, catalog freshness, and RTL-SDR serial 00000118.", "No audio: confirm the browser is allowed to play audio and that system/browser volume is raised; use Stop and Start after changing audio permissions.", "Unexpected device: run <font name='Courier'>rtl_test -d 00000118</font> and confirm the stable EEPROM serial.", "Clicking or underruns: confirm only one application owns the receiver/audio path and check the service audio status endpoint.", "Trial controls unavailable: wait for the five-minute countdown to expire, then use Restart Trial, or activate a valid N0JCG license."]), P("10. Audio/RF acceptance checklist", "H1N0"), *bullets(["Service reports product N0JCG Air Band Scanner and version 0.1.3.", "RTL-SDR serial 00000118 is detected and owned by this application.", "Full Airband and Nearby FAA scope controls change the scan set.", "FFT candidates are ranked and the strongest valid candidate is tuned.", "Direct Nearby FAA Tune starts browser audio and persists through silence timeout.", "Squelch closes/reopens audio and seven-second scanning release works.", "Pause, Block, Skip, and Clear all change channel eligibility as documented.", "Registration accepts the license S/N and registered email; registered installations hide trial status."]), P("For the detailed reusable receive settings and browser streaming model, see AIRBAND_AUDIO_RF_TEMPLATE.md in the repository.", "CalloutN0")]

doc = SimpleDocTemplate(str(OUT), pagesize=letter, rightMargin=0.85*inch, leftMargin=0.85*inch, topMargin=0.72*inch, bottomMargin=0.78*inch, title="N0JCG Air Band Scanner User Guide", author="N0JCG Open Radio Platform", subject="Installation, registration, operation, and troubleshooting", creator="N0JCG Open Radio Platform")
doc.build(story, onFirstPage=footer, onLaterPages=footer)
print(OUT)
