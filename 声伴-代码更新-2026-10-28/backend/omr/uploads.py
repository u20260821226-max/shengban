"""Bounded image upload envelope shared by local and public HTTP adapters."""
from email import policy
from email.parser import BytesParser

from .pdf_input import PDFInputError, render_pdf

MAX_IMAGE = 10 * 1024 * 1024
MAX_REQUEST = 64 * 1024 * 1024
LAYOUTS = {'vocal', 'piano'}


class UploadError(ValueError):
    def __init__(self, message, status=400):
        super().__init__(message)
        self.status = status


def decode_upload(raw, content_type):
    if not raw or len(raw) > MAX_REQUEST:
        raise UploadError('请上传 1 至 6 页，每页不超过 10 MB。', 413)
    if content_type == 'application/pdf':
        try:
            return render_pdf(raw), 'vocal'
        except PDFInputError as error:
            raise UploadError(str(error)) from error
    if content_type in {'image/jpeg', 'image/png'}:
        if len(raw) > MAX_IMAGE:
            raise UploadError('单页谱图不能超过 10 MB。', 413)
        return [raw], 'vocal'
    if not content_type.startswith('multipart/form-data;') or len(content_type) > 300:
        raise UploadError('仅支持 JPG、PNG 图片或一份 PDF。', 415)
    message = BytesParser(policy=policy.default).parsebytes(
        ('Content-Type: ' + content_type + '\r\nMIME-Version: 1.0\r\n\r\n').encode() + raw)
    if not message.is_multipart() or message.defects:
        raise UploadError('上传内容不完整，请重试。')
    parts, images, layout, seen_layout, pdf = list(message.iter_parts()), [], 'vocal', False, None
    if len(parts) > 7:
        raise UploadError('一次最多上传 6 页。', 413)
    for part in parts:
        if part.is_multipart() or part.defects or part.get_content_disposition() != 'form-data':
            raise UploadError('上传格式不正确，请重新选择图片。')
        name = part.get_param('name', header='content-disposition')
        payload = part.get_payload(decode=True) or b''
        if name == 'layout' and not seen_layout:
            try:
                layout = payload.decode('ascii')
            except UnicodeError:
                raise UploadError('请选择两行钢琴谱或三行声乐谱。')
            seen_layout = True
        elif name == 'images' and part.get_content_type() == 'application/pdf' and pdf is None:
            if not payload or len(payload) > MAX_IMAGE:
                raise UploadError('PDF 必须非空，且不超过 10 MB。', 413)
            pdf = payload
        elif name == 'images' and part.get_content_type() in {'image/jpeg', 'image/png'}:
            if not payload or len(payload) > MAX_IMAGE:
                raise UploadError('每页图片必须非空，且不超过 10 MB。', 413)
            images.append(payload)
        else:
            raise UploadError('请选择 JPG、PNG 图片，或单独上传一份 PDF。', 415)
    if pdf is not None:
        if images:
            raise UploadError('PDF 和图片请分开提交；一次选择一份 PDF 或 1 至 6 张图片。')
        if layout not in LAYOUTS:
            raise UploadError('请选择两行钢琴谱或三行声乐谱。')
        try:
            images = render_pdf(pdf)
        except PDFInputError as error:
            raise UploadError(str(error)) from error
    if layout not in LAYOUTS or not 1 <= len(images) <= 6:
        raise UploadError('请选择谱型，并上传 1 至 6 页同一首歌的谱图。')
    return images, layout
