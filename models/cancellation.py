# -*- coding: utf-8 -*-

from odoo import api, models, fields
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

  def clear_justification_date(self):
    """
    Quita la fecha de la justificación
    """
    self.justification_end_date = False

  def set_justification_to_june(self):
    """
    Asigna la fecha de la justificación a fonal de curso
    """
    pass

  def send_notification_mail(self):
    """
    Fuerza el envio de un mail de notificación al alumno
    """
    pass
