# -*- coding: utf-8 -*-

from odoo import api, models, fields
from odoo.exceptions import UserError
from odoo.tools.mail import email_normalize
from datetime import date

class Cancellation(models.Model):
  """
  Anulaciones de matrícula
  """
  _name = 'maya_students.cancellation'
  _description = 'Anulaciones de matrícula'

  # tipo de anulación, ordinaria o de oficio
  cancellation_type = fields.Selection([('ORD', 'Ordinaria'), ('OFC', 'Oficio')], required = True, default = 'ORD', string = 'Tipo')

  # situación de una anulación de oficio. Sólo para anulaciones de oficio
  situation = fields.Selection([
    ('0', ' '),
    ('1', 'Riesgo 1 - Sin notificar'),
    ('2', 'Riesgo 1 - Notificado'),
    ('3', 'Riesgo 2 - Pendiente de llamada'),
    ('4', 'Riesgo 2 - Llamada realizada'),
    ('5', 'Justificada'),
    ('6', 'Iniciado proceso de anulación'),
    ('7', 'Fin proceso de anulación'),
    ], string = 'Situación', default = '0',
    readonly = True)

  notification_date = fields.Date(string = 'Fecha de notificación por mail', 
                                help = 'Fecha de notificación por mail')

  query_date = fields.Datetime(string = 'Fecha de la consulta', 
                                help = 'Día y hora en el que se realizó la consulta a Moodle')

  lastaccess_date = fields.Datetime(string = 'Último acceso ', 
                                help = 'Día y hora del último acceso al curso')
  
  lastaccess_date_text = fields.Char(
    string="Última Conexión",
    compute='_compute_lastaccess_date_text'
  )

  # Hasta cuando está justificada su ausencia
  justification_end_date = fields.Date(string = 'Justificado hasta', 
                                help = 'Fecha fin de la ajustificación')

  comments = fields.Text(string = 'Comentarios',
                        help = 'Información relativa a la razón de la justificación')

  # Relación 1:1 con subject_student_rel
  subject_student_rel_id = fields.Many2one(
    'maya_core.subject_student_rel',
    required=True,
    ondelete='cascade',  # Si se borra el subject_student_rel, se borra esta anulacioón
  )

  student_name = fields.Char(string = 'Alumno', related = 'subject_student_rel_id.student_id.student_info')
  student_nia = fields.Char(string = 'NIA', related = 'subject_student_rel_id.student_id.nia')
  student_email = fields.Char(string = 'Email', related = 'subject_student_rel_id.student_id.email')
  student_email_support = fields.Char(string = 'Email de apoyo', related = 'subject_student_rel_id.student_id.email_support')
  student_email_corp = fields.Char(string = 'Email corporativo', related = 'subject_student_rel_id.student_id.email_coorp')
  subject_name = fields.Char(string = 'Módulo', related = 'subject_student_rel_id.subject_id.name', store = True)
  subject_course = fields.Char(string = 'Ciclo', related = 'subject_student_rel_id.course_id.abbr', store = True)

  related_cancellations_ids = fields.One2many('maya_students.cancellation',
    compute='_compute_related_cancellations',
    string='Otras anulaciones del alumno' 
  )  

  classroom_moodle_id = fields.Integer(string = 'Id aula Moodle')
  classroom_link = fields.Char(string = 'Enlace al aula', compute = '_compute_link_classroom')

  teacher_employee_ids = fields.Many2many('maya_core.employee',
        string='Profesorado asociado al módulo',
        compute='_compute_teacher_employees',
  )

  _sql_constraints = [(
    'unique_subject_student_rel_id',
    'unique(subject_student_rel_id)',
    'Cada relación Subject-Student sólo puede tener una anulación de matrícula.'
  )]

  @api.depends('subject_student_rel_id')
  def _compute_related_cancellations(self):
    """
    Obtiene las demás anulaciones del estudiante
    """  
    for record in self:
      student = record.subject_student_rel_id.student_id
      if student:
        # Buscar todas las anulaciones del mismo estudiante
        cancellations = self.search([
            ('subject_student_rel_id.student_id', '=', student.id),
            ('id', '!=', record.id)
        ])
        record.related_cancellations_ids = cancellations
      else:
        record.related_cancellations_ids = False

  @api.depends('lastaccess_date', 'query_date')
  def _compute_lastaccess_date_text(self):
    """
    Calcula el texto de la última conexión.
    """
    # fecha que consideramos como "Nunca"
    never_date = date(2000, 1, 1)

    for record in self:
      record.lastaccess_date_text = ""

      if not record.lastaccess_date:
        continue

      # Si la fecha es 1/1/2000
      if record.lastaccess_date.date() == never_date:
        record.lastaccess_date_text = "Nunca"
      else:
        fecha_str = record.lastaccess_date.strftime('%d/%m/%Y %H:%M')     
        n_dias_str = "N/D" # Valor por si 'query_date' no estuviera definida

        # Calculamos los días SÓLO si tenemos ambas fechas
        if record.query_date:
          # UsO .date() en ambas para calcular días completos
          delta = record.query_date.date() - record.lastaccess_date.date()
          n_dias = delta.days
          n_dias_str = str(n_dias)

        record.lastaccess_date_text = f"{fecha_str} ({n_dias_str} dias desde la última consulta)"

  @api.depends('classroom_moodle_id')
  def _compute_link_classroom(self):
    """
    Calcula la URL del aula
    """
    moodle_url = self.env['ir.config_parameter'].get_param('maya_core.moodle_url').rstrip('/') + '/'
    for record in self:
      if record.classroom_moodle_id:
        record.classroom_link = moodle_url + 'course/view.php?id=' + str(record.classroom_moodle_id)
      else:
        record.classroom_link = ''

  def clear_justification_date(self):
    """
    Quita la fecha de la justificación
    """
    self.justification_end_date = False

  def set_justification_to_june(self):
    """
    Asigna la fecha de la justificación a final de curso
    """
    today = fields.Date.today()
    current_year = today.year

    if today <= date(current_year, 8, 31):
      # 30 de Junio de ESTE año
      self.justification_end_date = date(current_year, 6, 30)
    else: # después del 31 de agosto, el 3o de junio del año que viene
      self.justification_end_date = date(current_year + 1, 6, 30)

  @api.depends('subject_student_rel_id.subject_id', 'subject_student_rel_id.course_id')
  def _compute_teacher_employees(self):
    """
    Calcula los registros maya_core.employee de los profesores
    asociados a este módulo y ciclo.
    """
    for record in self:
      if not record.subject_student_rel_id.subject_id or not record.subject_student_rel_id.course_id:
        record.teacher_employee_ids = False
        continue
                
      teacher_rel = self.env['maya_core.subject_employee_rel']
        
      teacher_rels = teacher_rel.search([
            ('subject_id', '=', self.subject_student_rel_id.subject_id.id),
            ('course_id', '=', self.subject_student_rel_id.course_id.id)
      ])
                        
      # De las relaciones encontradas, extraigo los profesores
      teacher_list = teacher_rels.mapped('employee_id') 
    
      # Filtro solo los que tienen email válido (deberian ser todos)
      valid_employees = teacher_list.filtered(lambda emp: email_normalize(emp.work_email))

      record.teacher_employee_ids = valid_employees


  def _get_teachers_reply_to_emails(self):
    """
    Busca todos los profesores asociados al módulo y ciclo
    de esta anulación y devuelve un string con sus emails 
    separados por coma.
    """
    self.ensure_one()
    
    email_list = self.teacher_employee_ids.mapped('work_email')

    # ya está compropbado que sean correctos
    return ','.join(email_list)
  
  
  def send_notification_mail_subject(self):
    """
    Fuerza el envio de un mail de notificación al alumno por una anulación
    """
    self.ensure_one()
    self.send_notification_mail()

    # para incluir a todos los módulos
    #record.with_context(include_all_modules=True).send_notification_mail()

  def send_notification_mail(self, include_all_subjects=False):
    """
    Fuerza el envio de un mail de notificación al alumno
    """
    self.ensure_one()

    # emails  TO, CC y REPLY
    email_to = self.student_email_corp if email_normalize(self.student_email_corp) else ''
    email_cc = ','.join([email for email in (self.student_email, self.student_email_support) if email_normalize(email)])
    reply_to = self._get_teachers_reply_to_emails()

    # compruebo que hay un email al menos
    if not self.student_email and not self.student_email_support and not self.student_email_corp:
      raise UserError(
          f"¡Acción no permitida! \n\n"
          f"El estudiante {self.student_name} no tiene ningún email configurado."
      )

    # Busco el servidor de correo del centro
    mail_alias = self.env['ir.config_parameter'].get_param('maya_core.alias_mail_center')
    if not mail_alias:
      print(f'\033[0;31m[ERROR]\033[0m No se ha definido el servidor de correo del centro')
      return
    
    mail_server = self.env['ir.mail_server'].search([('name', '=', mail_alias)], limit=1)
    if not mail_server:
        raise UserError(f"No se encontró el servidor de correo o no ha sido configurado {mail_alias}.")
    
    email_from = '"CEED Notificaciones" <'+ mail_server.smtp_user + '>' 

    email_values = {
        'email_from': email_from,
        'email_to': email_to,
        'email_cc': email_cc,
        'reply_to': reply_to,
        # por si existieran contactos en res.partner, que no los busque
        'recipient_ids': [], 
    }
    
    template = self.env.ref('maya_students.email_template_cancellation_risk1')

    render_context = {
        'include_all_subjects': include_all_subjects
    }

    template.mail_server_id = mail_server.id
    template.send_mail(self.id, force_send=True, 
                       email_values=email_values)

