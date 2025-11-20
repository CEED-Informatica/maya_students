# -*- coding: utf-8 -*-

from odoo import api, models, fields
from odoo.exceptions import UserError
import smtplib  
import socket   
from odoo.tools.mail import email_normalize
from datetime import date, datetime
from collections import defaultdict
import json
import logging

from ...maya_core.support.helper import get_mail_server

_logger = logging.getLogger(__name__)

ERROR_MAP = {
    "A01": "El alumno está matriculado en varios ciclos y, \
    al pertenecer este módulo a un aula compartida, no es posible \
    concretar a cual de ellos pertenece su matrícula.",
}

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
    ('2', 'Riesgo 1 - En proceso'),
    ('3', 'Riesgo 1 - Notificado'),
    ('4', 'Riesgo 2 - Pendiente de llamada'),
    ('5', 'Riesgo 2 - Llamada realizada'),
    ('6', 'Riesgo 3 - Dirección'),
    ('7', 'Justificada'),
    ('8', 'Iniciado proceso de anulación'),
    ('9', 'Módulo anulado de oficio'),
    ], string = 'Situación', default = '0',
    readonly = True)

  notification_date = fields.Date(string = 'Fecha de notificación', 
                                help = 'Fecha de notificación de alumno en riesgo 1 por mail')
  
  notification_date_r2 = fields.Date(string = 'Fecha de notificación', 
                                help = 'Fecha de notificación de alumno en riesgo 1 por mail')

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

  comments_r2 = fields.Text(string = 'Comentarios',
                        help = 'Información relativa a la notificación de R2')

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
  student_telephone1 = fields.Char(string = 'Teléfono 1', related = 'subject_student_rel_id.student_id.telephone1')
  student_telephone2 = fields.Char(string = 'Teléfono 2', related = 'subject_student_rel_id.student_id.telephone2')
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

  # para mostrar diferentes errores en pantalla
  error_codes = fields.Char(
    string="Códigos de error",
    default='',
    help="Códigos de error asociados a la anulación separados por comas"
  )

  error_descriptions = fields.Text(
    string="Errores detectados",
    compute="_compute_error_descriptions",
    store=False
  )

  _sql_constraints = [(
    'unique_subject_student_rel_id',
    'unique(subject_student_rel_id)',
    'Cada relación Subject-Student sólo puede tener una anulación de matrícula.'
  )]

  @api.depends('error_codes')
  def _compute_error_descriptions(self):
    for record in self:
      if not record.error_codes:
          record.error_descriptions = ""
          continue

      codes = [c.strip() for c in record.error_codes.split(',') if c.strip()]
      descs = [f"[{code}] {ERROR_MAP.get(code, 'Error desconocido')}" for code in codes]
      record.error_descriptions = "\n".join(descs)


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
            ('subject_id', '=', record.subject_student_rel_id.subject_id.id),
            ('course_id', '=', record.subject_student_rel_id.course_id.id)
      ])
                        
      # De las relaciones encontradas, extraigo los profesores
      teacher_list = teacher_rels.mapped('employee_id') 
    
      # Filtro solo los que tienen email válido (deberian ser todos)
      valid_employees = teacher_list.filtered(lambda emp: email_normalize(emp.work_email))

      record.teacher_employee_ids = valid_employees

  #################################
  #### ENVIO DE NOTIFICACIONES #### 
  #################################
  def _get_teachers_reply_to_emails(self, include_all_cancellations = False):
    """
    Busca todos los profesores asociados al módulo y ciclo
    de esta anulación y devuelve un string con sus emails 
    separados por coma.

    include_all_cancellations: si True incluye en el reply a todos los profesores 
    de todas las anulaciones relacionadas
    """
    self.ensure_one()

    # fuerza el compute de los profesores
    self.teacher_employee_ids  # asegura cálculo para el registro principal

    employees = self.teacher_employee_ids
    if include_all_cancellations:
      # fuerzo el compute de los profesores y añado a employee los nuevos
      for rel in self.related_cancellations_ids:
        rel.teacher_employee_ids
        employees |= rel.teacher_employee_ids
    
    email_list = employees.mapped('work_email')
    
    # comprobación de que son válidos
    valid = [email for email in (email_list or []) if email_normalize(email)]

    # Elimino profes duplicados
    seen = set()
    unique = []
    for e in valid:
      if e not in seen:
        seen.add(e)
        unique.append(e)

    return ','.join(unique)
  
  def _generate_mail_from_template(self, record, risk, mail_server, include_all_cancellations = False):
    """
    Genera (crea) un registro mail.mail a partir de la plantilla para el main_record.
    No hace cambios de estado aquí. Devuelve la mail.mail creada.
    - related_ids: lista de ids de anulaciones incluidas en este paquete (excluyendo el main).
    - include_all_subjects: si True se activa ctx include_all_modules para mostrar todas las subs.
    """
    self.ensure_one() 

    if risk == 'r1':
      template = self.env.ref('maya_students.email_template_cancellation_risk1')
    else:
      template = self.env.ref('maya_students.email_template_cancellation_risk2')
  
    # emails  TO, CC y REPLY
    email_from = f'"Notificaciones CEED" <{mail_server.smtp_user}>'
    email_to = record.student_email_corp if email_normalize(record.student_email_corp) else ''
    email_cc = ','.join([email for email in (record.student_email, record.student_email_support) if email_normalize(email)])
    reply_to = record._get_teachers_reply_to_emails(include_all_cancellations)

    email_values = {
      'email_from': email_from,
      'email_to': email_to,
      'email_cc': email_cc,
      'reply_to': reply_to,
      # por si existieran contactos en res.partner, que no los busque
      'recipient_ids': [], 
    }

    email_values['mail_server_id'] = mail_server.id

    # fuerza el compute de los profesores
    record.teacher_employee_ids

    if include_all_cancellations:
      for rel in record.related_cancellations_ids:
        rel.teacher_employee_ids  

    # Ponemos en contexto si queremos incluir todas las anulaciones del estudiante
    tmpl = template.with_context(include_all_cancellations = include_all_cancellations)

    # renderizo los elementos del template que son dionamicos 
    # (pongo el subject por si lo es en un futuro)
    # el resto de campos (CC, TOm, FROM...) los fijo por código, no están en plantilla
    subject_rendered = tmpl._render_field(
        'subject',  
        [record.id], 
    )
    
    body_rendered = tmpl._render_field(
        'body_html',  
        [record.id], 
    )

    email_data = email_values.copy()
    
    email_data.update({
        'subject': subject_rendered.get(record.id, ''),
        'body_html': body_rendered.get(record.id, ''),
        'model': template.model,
        'res_id': record.id,
    })

    return email_data
  
  def send_r1_notification_mail_subject(self):
    """
    Fuerza el envío de un mail de notificación al alumno por una anulación en riesgo 1 
    """
    self.send_notification_mail_subject('r1')

  def send_r2_notification_mail_subject(self):
    """
    Fuerza el envío de un mail de notificación al alumno por una anulación en riesgo 2 
    """
    self.send_notification_mail_subject('r2')

    ## TODO completar la fecha y las observaciones del riesgo 2



  def send_notification_mail_subject(self, risk):
    """
    Fuerza el envío de un mail de notificación al alumno por una anulación
    """
    self.ensure_one()

    # compruebo que haya un email al menos
    student_email_ok = any([email_normalize(x) for x in (self.student_email_corp, self.student_email, self.student_email_support) if x])
    if not student_email_ok:
      raise UserError(
          f"¡Acción no permitida! \n\n"
          f"El estudiante {self.student_name} no tiene ningún email configurado."
      )

    email_data = self._generate_mail_from_template(self, risk,
                                      get_mail_server(self, 'centro'), 
                                      include_all_cancellations = False)

    try:
      mail = self.env['mail.mail'].create(email_data)
      mail.send()
      
      self.write({
        'situation': '3',  # -> 'Riesgo 1 - Notificado'
        'notification_date': datetime.now().date()
      })

      message = f'Mensaje enviado correctamente a [{self.student_nia}] {self.student_name}. '  

      return {
        'type': 'ir.actions.client',
        'tag': 'display_notification',
        'params': {
            'title': 'Notificación enviada',
            'message': message,
            'type': 'info',  # 'success', 'warning', 'danger', 'info'
            'sticky': False,
        }
      }
    
    # no hace falta que revierta nada si hay error ya que la situation sigue estando en '1'
    except UserError as e:
      # error de Odoo (plantilla mal configurada, faltan datos...)
      _logger.warning(f"Error al enviar email a {self.student_name}: {str(e)}")
      raise e

    except (smtplib.SMTPException, socket.error) as e:
      # error de red o del Servidor SMTP (no hay conexión, auth fallida...)
      _logger.error(f"Error de Red/SMTP al enviar email a {self.student_name}: {str(e)}")
      raise UserError(f"No se pudo contactar con el servidor de correo. Error: {str(e)}")

    except Exception as e:
      # cualquier otro error inesperado
      _logger.error(f"Error inesperado al enviar email a {self.student_name}: {str(e)}")
      raise UserError(f"Ocurrió un error inesperado al enviar el correo: {str(e)}")

  def send_notification_mail_subject_agruped(self):
    """
    Prepara y envia de manera agrupada por NIA los mensajes de 
    notificación de las anulaciones de oficio
    """
    ## TODO parametrizae
    NUM_DIAS_AVISO = 2

    skipped = []        # lista de tuplas (id, motivo) de anulaciones que se saltan
    already_processed_in_memory = set()  # ids de cancellations ya incluidas en paquetes para ser notificadas (evita duplicados)
    generation_errors = [] # errores de generación de correos

    # Estructuras para generar mails y mapear paquetes (están pareadas).
    mails_to_create = []   # lista de dicts con email_values
    packages = []          # lista de dicts {'main_id': int, 'related_ids': [int,...]} para cambiar la situation si el envio ha sido correcto
    
    mail_server = get_mail_server(self, 'centro')
    today = fields.Date.today()

    for record in self:
      # Ausencias justificadas
      if record.situation == '7':  
      
        # si justificada y fecha vigente -> ignorar
        if record.justification_end_date and today <= record.justification_end_date:
          skipped.append((record.id, 'justificada_vigente'))
          continue
        else:
          # caducada -> pasar a '1' para procesarse en este bucle
          try:
            record.write({'situation': '1'})
          except Exception as e:
            _logger.error(f"Error escribiendo situación '1' para {record.id}: {str(e)}")
            skipped.append((record.id, 'error_write_6->1'))
            continue

      # ya está notificada
      elif record.situation == '3':
        if record.notification_date:
          days = (today - record.notification_date).days
          if days >= NUM_DIAS_AVISO:
            try:
              record.write({'situation': '4'})  # pasa a pendiente de llamada
              skipped.append((record.id, 'R1_notificada->R2_pendiente'))
              continue
            except Exception as e:
              _logger.error(f"Error escribiendo situación '4' para {record.id}: {str(e)}")
              skipped.append((record.id, 'error_write_3->4'))
          else:
              skipped.append((record.id, f'notificada_reciente_{days}d'))
        else:
          # sin fecha, por seguridad la ignorao, aunque no debería de ocurrir
          skipped.append((record.id, '3_sin_fecha'))
          continue

      # Llegados a este punto, cualquier situation que no sea R1 sin notificar, no se procesa)
      elif record.situation != '1':
        skipped.append((record.id, f'no_envio_sit_{record.situation}'))
        continue
        
      # Sin notificación -> vamos a preparar paquete
      # Seleccionamos related a incluir: relacionadas que no estén ya en '2' ni en '3'
      # El resto de situaciones ya estarían contempladas
      related_to_include = record.related_cancellations_ids.filtered(lambda c: c.situation == '1' and c.id not in already_processed_in_memory)

      # compruebo que haya un email al menos
      student_email_ok = any([email_normalize(x) for x in (record.student_email_corp, record.student_email, record.student_email_support) if x])
      if not student_email_ok:
        skipped.append((record.id, 'sin_email'))
        continue

      # Marco el registro y sus relacionados como '2' para que no 
      # se procesen en otro proceso
      try:
        # el registro actual
        record.write({'situation': '2'})
        # marcamos related -> '2' (si los hay)
        if related_to_include:
          related_to_include.write({'situation': '2'})
      except Exception as e:
        _logger.error(f"Error poniendo en proceso de notificación la anulación (1->2) {record.id}: {str(e)}")
        # si falla la escritura, revertimos cualquier write parcial y saltamos
        try:
          record.write({'situation': '1'})
          if related_to_include:
            related_to_include.write({'situation': '1'})
        except Exception:
          pass

        skipped.append((record.id, f'error_en_proceso_1->2:{str(e)}'))
        continue

      # Las añado al set para no incluirlas dos veces
      already_processed_in_memory.add(record.id)
      for r in related_to_include:
        already_processed_in_memory.add(r.id)

      # genero el email_values con el template (no se envía aún)
      try:
        email_values = record._generate_mail_from_template(record, mail_server, include_all_cancellations=True)
        
        mails_to_create.append(email_values)
        packages.append({
            'main_id': record.id,
            'related_ids': related_to_include.ids,
        })
      except Exception as e:
        _logger.error(f"Error generando mail para anulación {record.id}: {str(e)}")
        generation_errors.append((record.id, str(e)))

        # revierto las anulaciones "en proceso" para permitir reprocesarlo luego
        try:
          record.write({'situation': '1'})
          if related_to_include:
            related_to_include.write({'situation': '1'})
        except Exception as e2:
            _logger.error(f"Error revirtiendo situación tras fallo generación para {record.id}: {str(e2)}")
        continue


    # Notificaciones para los profesores
    # Anulaciones en 'Riesgo 2 Por notificar'
    self.create_notification_items(skipped,self.env.ref('maya_students.notification_group_exofficio_cancellations').id)



    total_created = 0 # numero de notificaciones creadas (ojo! no enviadas, que por una notificación puede haber vbarios remitentes)
    total_sent = 0
    total_failed = 0

    # envio de correos
    if mails_to_create:
      try:
        created_mail_records = self.env['mail.mail'].create(mails_to_create)
      except Exception as e:
        # fallo criticó creando mails en BD: revierto todas las reservas hechas
        _logger.error(f"Error creando registros mail.mail: {str(e)}")
        
        for pkg in packages:
          try:
              self.browse([pkg['main_id']] + pkg.get('related_ids', [])).write({'situation': '1'})
          except Exception as e2:
              _logger.error(f"Error revirtiendo paquete {pkg}: {e2}")
        raise UserError(f"Error creando los mensajes de correo: {str(e)}")

      total_created = len(created_mail_records)

      # Envio de mail y actualizo situation en función del resultado
      for mail_rec, pkg in zip(created_mail_records, packages):
        main_id = pkg.get('main_id')
        related_ids = pkg.get('related_ids', [])
        try:
          mail_rec.send()
          total_sent += 1

          # si ha ido bien situation -> '3'
          try:
            self.browse(main_id).write({
                'situation': '3',
                'notification_date': today
            })
          except Exception as e:
            _logger.error(f"No se pudo poner la anulación {main_id} a 'R1 - notificada' tras el envío: {str(e)}")

          if related_ids:
            try:
              self.browse(related_ids).write({'situation': '3'})
            except Exception as e:
              _logger.error(f"No se pudo poner ralgunas de las anulaciones relacionadas {related_ids} a 'R1 - notificada' tras envío: {str(e)}")

        except (smtplib.SMTPException, socket.error) as e:
          total_failed += 1
          _logger.error(f"Error de Red/SMTP al enviar email a {mail_rec.id} para la anulación {main_id}: {str(e)}")
          # Cambio la situation a '1' para permitir reintento (podrían estar en '2')
          try:
            self.browse([main_id] + related_ids).write({'situation': '1'})
          except Exception as e2:
            _logger.error(f"Error revirtiendo situación a 'R1 - sin notificar' para la anulación {main_id}: {str(e2)}")

        except Exception as e:
          total_failed += 1
          _logger.error(f"Error inesperado enviando mail id {mail_rec.id} para la anulación {main_id}: {str(e)}")
          try:
            self.browse([main_id] + related_ids).write({'situation': '1'})
          except Exception as e2:
            _logger.error(f"Error revirtiendo situación a '1' para la anuladción {main_id}: {str(e2)}")

    # info sobre generation_errors y skipped
    if generation_errors:
        _logger.warning(f"Errores generando correo: {generation_errors}")
    if skipped:
        _logger.info(f"Anulaciones no procesadas: {skipped}")

    # Finalmente mostramos notificación UI
    msg = (f"Mensajes creados: {total_created}. Enviados: {total_sent}. Fallidos: {total_failed}. "
           f"Omitidos: {len(skipped)}. Errores generación: {len(generation_errors)}.")
    return {
        'type': 'ir.actions.client',
        'tag': 'display_notification',
        'params': {
            'title': 'Proceso de notificaciones agrupadas completado',
            'message': msg,
            'type': 'success' if total_failed == 0 and len(generation_errors) == 0 else 'warning',
            'sticky': False,
        }
    }

  @api.model
  def create_notification_items(self, skipped_list, ngroup_id):
    """
    A partir de la lista de elementos saltados en el envio de notificación a los alumnos
    se crean las notificaciones para que los profesores hagan las llamadas

    :skipped_list lista de tuplas (cancellation_id, tag_string)
    :ngroup_id id del grupo de notificaciones (maya_core.notification_group)
    """

    provider_id = self.env.ref('maya_students.notification_provider').id

    # Filtro las anulaciones que están en situacn de R2 por llamar
    cancellation_ids = [c_id for (c_id, tag) in skipped_list]
    cancellations = self.env['maya_students.cancellation'].search([
        ('id', 'in', cancellation_ids),
        ('situation', '=', '4')
    ])

    if not cancellations:
      return
    
    base_url = self.env['ir.config_parameter'].get_param('web.base.url').rstrip('/') + '/'

    # Las agrupo por profesor, ciclo y módulo
    # (user.id, course.id, subject.id) → [cancellations...]
    grouped = defaultdict(list)   

    for c in cancellations:
      c.teacher_employee_ids # fuerzo el compute de los empleados
      course = c.subject_student_rel_id.course_id
      subject = c.subject_student_rel_id.subject_id

      for teacher in c.teacher_employee_ids:
        user = teacher.user_id
        if not user:
          continue

        key = (user.id, course.id, subject.id) 
        if c not in grouped[key]:
          grouped[key].append(c)

    # Creo las notificaciones
    for key, cancels in grouped.items():
      course = self.env['maya_core.course'].browse(key[1]) if key[1] else None
      subject = self.env['maya_core.subject'].browse(key[2]) if key[2] else None
      user_email = self.env['res.users'].browse(key[0]).email

      course_abbr = course.abbr if course and course.exists() and course.abbr else ''
      subject_name = subject.name if subject and subject.exists() and subject.name else ''

      summary = f'[{course_abbr}] - {subject_name}'
      to = 'llamadas pendientes a estudiantes' if len(cancels) > 1 else 'llamada pendiente a un estudiante'
      body = f'Tienes {len(cancels)} {to} en riesgo 2 de abandono (R2)'

      urls = [ f'{base_url}/web?reload=true#id={c.id}&menu_id=289&model=maya_students.cancellation&view_type=form'
               for c in cancels]

      self.env['maya_core.notification_item'].create({
          'provider_id': provider_id,
          'user_id': key[0],
          'ngroup_id': ngroup_id,
          "priority": "3",
          "summary": summary,
          "body": body, 
          "link_objects": urls
      })

    
  def action_download_cancellation_r3_file(self):
    print("bahjo cosas")
    return