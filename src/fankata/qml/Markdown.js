.pragma library
// Inline Markdown subset used by Troubleshoot fans (requirement 4.7.5):
// **bold**, *italic*, `code` and [links](url), turned into Qt rich text.
function esc(s) { return String(s).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;") }
function inline(src, c) {
    const re = /\*\*(.+?)\*\*|`(.+?)`|\[(.+?)\]\((.+?)\)|\*(.+?)\*/g
    let out = "", i = 0, m
    while ((m = re.exec(src)) !== null) {
        out += esc(src.slice(i, m.index))
        if (m[1] !== undefined) out += "<b>" + esc(m[1]) + "</b>"
        else if (m[2] !== undefined)
            out += "<span style=\"font-family:'" + c.mono + "'; background-color:" + c.codeBg + "; color:" + c.code + "\">&nbsp;"
                   + esc(m[2]).replace(/ /g, "&nbsp;") + "&nbsp;</span>"
        else if (m[3] !== undefined)
            out += "<a href=\"" + esc(m[4]) + "\" style=\"color:" + c.link + "; text-decoration:none\"><b>" + esc(m[3]) + "</b></a>"
        else out += "<i>" + esc(m[5]) + "</i>"
        i = re.lastIndex
    }
    return out + esc(src.slice(i))
}
