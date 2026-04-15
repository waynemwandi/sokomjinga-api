# app/services/email_templates/base.py
def render_email_layout(title: str, content_html: str, cta_html: str = "") -> str:
    return f"""
    <html>
        <body style="margin:0; padding:0; background-color:#000000; font-family:Arial, Helvetica, sans-serif;">
            <table width="100%" cellpadding="0" cellspacing="0" border="0" style="background-color:#000000; padding:32px 16px;">
            <tr>
                <td align="center">
                <table width="640" cellpadding="0" cellspacing="0" border="0" style="width:640px; max-width:640px; background-color:#111111; border:1px solid #1f1f1f; border-radius:16px;">
                    <tr>
                    <td style="padding:28px 28px 12px 28px; color:#ffffff; font-size:18px; font-weight:700;">
                        MaoniMarket
                    </td>
                    </tr>

                    <tr>
                    <td style="padding:0 28px 4px 28px; color:#ffffff; font-size:16px; font-weight:700;">
                        {title}
                    </td>
                    </tr>

                    <tr>
                    <td style="padding:0 28px;">
                        <div style="border-top:1px solid #222222; line-height:1px; font-size:1px;">&nbsp;</div>
                    </td>
                    </tr>

                    <tr>
                    <td style="padding:24px 28px 0 28px; color:#ffffff; font-size:14px; line-height:22px;">
                        {content_html}
                    </td>
                    </tr>

                    {"<tr><td align='center' style='padding:28px;'>" + cta_html + "</td></tr>" if cta_html else ""}

                    <tr>
                    <td style="padding:0 28px 28px 28px; color:#737373; font-size:12px; line-height:18px; text-align:center;">
                        You are receiving this email because you interacted with MaoniMarket.
                    </td>
                    </tr>
                </table>
                </td>
            </tr>
            </table>
        </body>
    </html>
    """