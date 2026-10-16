//
// Generated file, do not edit! Created by opp_msgtool 6.4 from TaskPacket.msg.
//

// Disable warnings about unused variables, empty switch stmts, etc:
#ifdef _MSC_VER
#  pragma warning(disable:4101)
#  pragma warning(disable:4065)
#endif

#if defined(__clang__)
#  pragma clang diagnostic ignored "-Wshadow"
#  pragma clang diagnostic ignored "-Wconversion"
#  pragma clang diagnostic ignored "-Wunused-parameter"
#  pragma clang diagnostic ignored "-Wc++98-compat"
#  pragma clang diagnostic ignored "-Wunreachable-code-break"
#  pragma clang diagnostic ignored "-Wold-style-cast"
#elif defined(__GNUC__)
#  pragma GCC diagnostic ignored "-Wshadow"
#  pragma GCC diagnostic ignored "-Wconversion"
#  pragma GCC diagnostic ignored "-Wunused-parameter"
#  pragma GCC diagnostic ignored "-Wold-style-cast"
#  pragma GCC diagnostic ignored "-Wsuggest-attribute=noreturn"
#  pragma GCC diagnostic ignored "-Wfloat-conversion"
#endif

#include <iostream>
#include <sstream>
#include <memory>
#include <type_traits>
#include "TaskPacket_m.h"

namespace omnetpp {

// Template pack/unpack rules. They are declared *after* a1l type-specific pack functions for multiple reasons.
// They are in the omnetpp namespace, to allow them to be found by argument-dependent lookup via the cCommBuffer argument

// Packing/unpacking an std::vector
template<typename T, typename A>
void doParsimPacking(omnetpp::cCommBuffer *buffer, const std::vector<T,A>& v)
{
    int n = v.size();
    doParsimPacking(buffer, n);
    for (int i = 0; i < n; i++)
        doParsimPacking(buffer, v[i]);
}

template<typename T, typename A>
void doParsimUnpacking(omnetpp::cCommBuffer *buffer, std::vector<T,A>& v)
{
    int n;
    doParsimUnpacking(buffer, n);
    v.resize(n);
    for (int i = 0; i < n; i++)
        doParsimUnpacking(buffer, v[i]);
}

// Packing/unpacking an std::list
template<typename T, typename A>
void doParsimPacking(omnetpp::cCommBuffer *buffer, const std::list<T,A>& l)
{
    doParsimPacking(buffer, (int)l.size());
    for (typename std::list<T,A>::const_iterator it = l.begin(); it != l.end(); ++it)
        doParsimPacking(buffer, (T&)*it);
}

template<typename T, typename A>
void doParsimUnpacking(omnetpp::cCommBuffer *buffer, std::list<T,A>& l)
{
    int n;
    doParsimUnpacking(buffer, n);
    for (int i = 0; i < n; i++) {
        l.push_back(T());
        doParsimUnpacking(buffer, l.back());
    }
}

// Packing/unpacking an std::set
template<typename T, typename Tr, typename A>
void doParsimPacking(omnetpp::cCommBuffer *buffer, const std::set<T,Tr,A>& s)
{
    doParsimPacking(buffer, (int)s.size());
    for (typename std::set<T,Tr,A>::const_iterator it = s.begin(); it != s.end(); ++it)
        doParsimPacking(buffer, *it);
}

template<typename T, typename Tr, typename A>
void doParsimUnpacking(omnetpp::cCommBuffer *buffer, std::set<T,Tr,A>& s)
{
    int n;
    doParsimUnpacking(buffer, n);
    for (int i = 0; i < n; i++) {
        T x;
        doParsimUnpacking(buffer, x);
        s.insert(x);
    }
}

// Packing/unpacking an std::map
template<typename K, typename V, typename Tr, typename A>
void doParsimPacking(omnetpp::cCommBuffer *buffer, const std::map<K,V,Tr,A>& m)
{
    doParsimPacking(buffer, (int)m.size());
    for (typename std::map<K,V,Tr,A>::const_iterator it = m.begin(); it != m.end(); ++it) {
        doParsimPacking(buffer, it->first);
        doParsimPacking(buffer, it->second);
    }
}

template<typename K, typename V, typename Tr, typename A>
void doParsimUnpacking(omnetpp::cCommBuffer *buffer, std::map<K,V,Tr,A>& m)
{
    int n;
    doParsimUnpacking(buffer, n);
    for (int i = 0; i < n; i++) {
        K k; V v;
        doParsimUnpacking(buffer, k);
        doParsimUnpacking(buffer, v);
        m[k] = v;
    }
}

// Default pack/unpack function for arrays
template<typename T>
void doParsimArrayPacking(omnetpp::cCommBuffer *b, const T *t, int n)
{
    for (int i = 0; i < n; i++)
        doParsimPacking(b, t[i]);
}

template<typename T>
void doParsimArrayUnpacking(omnetpp::cCommBuffer *b, T *t, int n)
{
    for (int i = 0; i < n; i++)
        doParsimUnpacking(b, t[i]);
}

// Default rule to prevent compiler from choosing base class' doParsimPacking() function
template<typename T>
void doParsimPacking(omnetpp::cCommBuffer *, const T& t)
{
    throw omnetpp::cRuntimeError("Parsim error: No doParsimPacking() function for type %s", omnetpp::opp_typename(typeid(t)));
}

template<typename T>
void doParsimUnpacking(omnetpp::cCommBuffer *, T& t)
{
    throw omnetpp::cRuntimeError("Parsim error: No doParsimUnpacking() function for type %s", omnetpp::opp_typename(typeid(t)));
}

}  // namespace omnetpp


template<typename T>
std::string toStringIfPrintable(const T& t) {
    if constexpr (omnetpp::internal::is_printable<T>::value) {
        std::ostringstream os;
        os << t;
        return os.str();
    }
    return omnetpp::cClassDescriptor::UNPRINTABLE;
}

template<typename T>
bool fromStringIfExtractable(T& t, const char *s) {
    if constexpr (omnetpp::internal::is_extractable<T>::value) {
        std::istringstream is(s);
        is >> t;
        return true;
    }
    return false;
}

namespace v2x {

Register_Class(TaskChunk)

TaskChunk::TaskChunk() : ::inet::FieldsChunk()
{
}

TaskChunk::TaskChunk(const TaskChunk& other) : ::inet::FieldsChunk(other)
{
    copy(other);
}

TaskChunk::~TaskChunk()
{
}

TaskChunk& TaskChunk::operator=(const TaskChunk& other)
{
    if (this == &other) return *this;
    ::inet::FieldsChunk::operator=(other);
    copy(other);
    return *this;
}

void TaskChunk::copy(const TaskChunk& other)
{
    this->taskId = other.taskId;
    this->clientId = other.clientId;
    this->serverId = other.serverId;
    this->response = other.response;
    this->critical = other.critical;
    this->createdAt = other.createdAt;
    this->deadlineAt = other.deadlineAt;
    this->workUnits = other.workUnits;
    this->queueSeconds = other.queueSeconds;
    this->responseBytes = other.responseBytes;
    this->telemetry = other.telemetry;
    this->subscribe = other.subscribe;
    this->unsubscribe = other.unsubscribe;
    this->reportSequence = other.reportSequence;
    this->reportGeneratedAt = other.reportGeneratedAt;
    this->reportBusyUntil = other.reportBusyUntil;
}

void TaskChunk::parsimPack(omnetpp::cCommBuffer *b) const
{
    ::inet::FieldsChunk::parsimPack(b);
    doParsimPacking(b,this->taskId);
    doParsimPacking(b,this->clientId);
    doParsimPacking(b,this->serverId);
    doParsimPacking(b,this->response);
    doParsimPacking(b,this->critical);
    doParsimPacking(b,this->createdAt);
    doParsimPacking(b,this->deadlineAt);
    doParsimPacking(b,this->workUnits);
    doParsimPacking(b,this->queueSeconds);
    doParsimPacking(b,this->responseBytes);
    doParsimPacking(b,this->telemetry);
    doParsimPacking(b,this->subscribe);
    doParsimPacking(b,this->unsubscribe);
    doParsimPacking(b,this->reportSequence);
    doParsimPacking(b,this->reportGeneratedAt);
    doParsimPacking(b,this->reportBusyUntil);
}

void TaskChunk::parsimUnpack(omnetpp::cCommBuffer *b)
{
    ::inet::FieldsChunk::parsimUnpack(b);
    doParsimUnpacking(b,this->taskId);
    doParsimUnpacking(b,this->clientId);
    doParsimUnpacking(b,this->serverId);
    doParsimUnpacking(b,this->response);
    doParsimUnpacking(b,this->critical);
    doParsimUnpacking(b,this->createdAt);
    doParsimUnpacking(b,this->deadlineAt);
    doParsimUnpacking(b,this->workUnits);
    doParsimUnpacking(b,this->queueSeconds);
    doParsimUnpacking(b,this->responseBytes);
    doParsimUnpacking(b,this->telemetry);
    doParsimUnpacking(b,this->subscribe);
    doParsimUnpacking(b,this->unsubscribe);
    doParsimUnpacking(b,this->reportSequence);
    doParsimUnpacking(b,this->reportGeneratedAt);
    doParsimUnpacking(b,this->reportBusyUntil);
}

int TaskChunk::getTaskId() const
{
    return this->taskId;
}

void TaskChunk::setTaskId(int taskId)
{
    handleChange();
    this->taskId = taskId;
}

int TaskChunk::getClientId() const
{
    return this->clientId;
}

void TaskChunk::setClientId(int clientId)
{
    handleChange();
    this->clientId = clientId;
}

int TaskChunk::getServerId() const
{
    return this->serverId;
}

void TaskChunk::setServerId(int serverId)
{
    handleChange();
    this->serverId = serverId;
}

bool TaskChunk::getResponse() const
{
    return this->response;
}

void TaskChunk::setResponse(bool response)
{
    handleChange();
    this->response = response;
}

bool TaskChunk::getCritical() const
{
    return this->critical;
}

void TaskChunk::setCritical(bool critical)
{
    handleChange();
    this->critical = critical;
}

::omnetpp::simtime_t TaskChunk::getCreatedAt() const
{
    return this->createdAt;
}

void TaskChunk::setCreatedAt(::omnetpp::simtime_t createdAt)
{
    handleChange();
    this->createdAt = createdAt;
}

::omnetpp::simtime_t TaskChunk::getDeadlineAt() const
{
    return this->deadlineAt;
}

void TaskChunk::setDeadlineAt(::omnetpp::simtime_t deadlineAt)
{
    handleChange();
    this->deadlineAt = deadlineAt;
}

double TaskChunk::getWorkUnits() const
{
    return this->workUnits;
}

void TaskChunk::setWorkUnits(double workUnits)
{
    handleChange();
    this->workUnits = workUnits;
}

double TaskChunk::getQueueSeconds() const
{
    return this->queueSeconds;
}

void TaskChunk::setQueueSeconds(double queueSeconds)
{
    handleChange();
    this->queueSeconds = queueSeconds;
}

int TaskChunk::getResponseBytes() const
{
    return this->responseBytes;
}

void TaskChunk::setResponseBytes(int responseBytes)
{
    handleChange();
    this->responseBytes = responseBytes;
}

bool TaskChunk::getTelemetry() const
{
    return this->telemetry;
}

void TaskChunk::setTelemetry(bool telemetry)
{
    handleChange();
    this->telemetry = telemetry;
}

bool TaskChunk::getSubscribe() const
{
    return this->subscribe;
}

void TaskChunk::setSubscribe(bool subscribe)
{
    handleChange();
    this->subscribe = subscribe;
}

bool TaskChunk::getUnsubscribe() const
{
    return this->unsubscribe;
}

void TaskChunk::setUnsubscribe(bool unsubscribe)
{
    handleChange();
    this->unsubscribe = unsubscribe;
}

int TaskChunk::getReportSequence() const
{
    return this->reportSequence;
}

void TaskChunk::setReportSequence(int reportSequence)
{
    handleChange();
    this->reportSequence = reportSequence;
}

::omnetpp::simtime_t TaskChunk::getReportGeneratedAt() const
{
    return this->reportGeneratedAt;
}

void TaskChunk::setReportGeneratedAt(::omnetpp::simtime_t reportGeneratedAt)
{
    handleChange();
    this->reportGeneratedAt = reportGeneratedAt;
}

::omnetpp::simtime_t TaskChunk::getReportBusyUntil() const
{
    return this->reportBusyUntil;
}

void TaskChunk::setReportBusyUntil(::omnetpp::simtime_t reportBusyUntil)
{
    handleChange();
    this->reportBusyUntil = reportBusyUntil;
}

class TaskChunkDescriptor : public omnetpp::cClassDescriptor
{
  private:
    mutable const char **propertyNames;
    enum FieldConstants {
        FIELD_taskId,
        FIELD_clientId,
        FIELD_serverId,
        FIELD_response,
        FIELD_critical,
        FIELD_createdAt,
        FIELD_deadlineAt,
        FIELD_workUnits,
        FIELD_queueSeconds,
        FIELD_responseBytes,
        FIELD_telemetry,
        FIELD_subscribe,
        FIELD_unsubscribe,
        FIELD_reportSequence,
        FIELD_reportGeneratedAt,
        FIELD_reportBusyUntil,
    };
  public:
    TaskChunkDescriptor();
    virtual ~TaskChunkDescriptor();

    virtual bool doesSupport(omnetpp::cObject *obj) const override;
    virtual const char **getPropertyNames() const override;
    virtual const char *getProperty(const char *propertyName) const override;
    virtual std::string getValueAsString(omnetpp::any_ptr object) const override;
    virtual void setValueAsString(omnetpp::any_ptr object, const char *value) const override;
    virtual int getFieldCount() const override;
    virtual const char *getFieldName(int field) const override;
    virtual int findField(const char *fieldName) const override;
    virtual unsigned int getFieldTypeFlags(int field) const override;
    virtual const char *getFieldTypeString(int field) const override;
    virtual const char **getFieldPropertyNames(int field) const override;
    virtual const char *getFieldProperty(int field, const char *propertyName) const override;
    virtual int getFieldArraySize(omnetpp::any_ptr object, int field) const override;
    virtual void setFieldArraySize(omnetpp::any_ptr object, int field, int size) const override;

    virtual const char *getFieldDynamicTypeString(omnetpp::any_ptr object, int field, int i) const override;
    virtual std::string getFieldValueAsString(omnetpp::any_ptr object, int field, int i) const override;
    virtual void setFieldValueAsString(omnetpp::any_ptr object, int field, int i, const char *value) const override;
    virtual omnetpp::cValue getFieldValue(omnetpp::any_ptr object, int field, int i) const override;
    virtual void setFieldValue(omnetpp::any_ptr object, int field, int i, const omnetpp::cValue& value) const override;

    virtual const char *getFieldStructName(int field) const override;
    virtual omnetpp::any_ptr getFieldStructValuePointer(omnetpp::any_ptr object, int field, int i) const override;
    virtual void setFieldStructValuePointer(omnetpp::any_ptr object, int field, int i, omnetpp::any_ptr ptr) const override;
};

Register_ClassDescriptor(TaskChunkDescriptor)

TaskChunkDescriptor::TaskChunkDescriptor() : omnetpp::cClassDescriptor(omnetpp::opp_typename(typeid(v2x::TaskChunk)), "inet::FieldsChunk")
{
    propertyNames = nullptr;
}

TaskChunkDescriptor::~TaskChunkDescriptor()
{
    delete[] propertyNames;
}

bool TaskChunkDescriptor::doesSupport(omnetpp::cObject *obj) const
{
    return dynamic_cast<TaskChunk *>(obj)!=nullptr;
}

const char **TaskChunkDescriptor::getPropertyNames() const
{
    if (!propertyNames) {
        static const char *names[] = {  nullptr };
        omnetpp::cClassDescriptor *base = getBaseClassDescriptor();
        const char **baseNames = base ? base->getPropertyNames() : nullptr;
        propertyNames = mergeLists(baseNames, names);
    }
    return propertyNames;
}

const char *TaskChunkDescriptor::getProperty(const char *propertyName) const
{
    omnetpp::cClassDescriptor *base = getBaseClassDescriptor();
    return base ? base->getProperty(propertyName) : nullptr;
}

std::string TaskChunkDescriptor::getValueAsString(omnetpp::any_ptr object) const
{
    TaskChunk *pp = omnetpp::fromAnyPtr<TaskChunk>(object); (void)pp;
    return ((cObject*)pp)->str();
}

void TaskChunkDescriptor::setValueAsString(omnetpp::any_ptr object, const char *value) const
{
    TaskChunk *pp = omnetpp::fromAnyPtr<TaskChunk>(object); (void)pp;
    if (!fromStringIfExtractable(*pp, value))
        cClassDescriptor::setValueAsString(object, value);
}

int TaskChunkDescriptor::getFieldCount() const
{
    omnetpp::cClassDescriptor *base = getBaseClassDescriptor();
    return base ? 16+base->getFieldCount() : 16;
}

unsigned int TaskChunkDescriptor::getFieldTypeFlags(int field) const
{
    omnetpp::cClassDescriptor *base = getBaseClassDescriptor();
    if (base) {
        if (field < base->getFieldCount())
            return base->getFieldTypeFlags(field);
        field -= base->getFieldCount();
    }
    static unsigned int fieldTypeFlags[] = {
        FD_ISEDITABLE,    // FIELD_taskId
        FD_ISEDITABLE,    // FIELD_clientId
        FD_ISEDITABLE,    // FIELD_serverId
        FD_ISEDITABLE,    // FIELD_response
        FD_ISEDITABLE,    // FIELD_critical
        FD_ISEDITABLE,    // FIELD_createdAt
        FD_ISEDITABLE,    // FIELD_deadlineAt
        FD_ISEDITABLE,    // FIELD_workUnits
        FD_ISEDITABLE,    // FIELD_queueSeconds
        FD_ISEDITABLE,    // FIELD_responseBytes
        FD_ISEDITABLE,    // FIELD_telemetry
        FD_ISEDITABLE,    // FIELD_subscribe
        FD_ISEDITABLE,    // FIELD_unsubscribe
        FD_ISEDITABLE,    // FIELD_reportSequence
        FD_ISEDITABLE,    // FIELD_reportGeneratedAt
        FD_ISEDITABLE,    // FIELD_reportBusyUntil
    };
    return (field >= 0 && field < 16) ? fieldTypeFlags[field] : 0;
}

const char *TaskChunkDescriptor::getFieldName(int field) const
{
    omnetpp::cClassDescriptor *base = getBaseClassDescriptor();
    if (base) {
        if (field < base->getFieldCount())
            return base->getFieldName(field);
        field -= base->getFieldCount();
    }
    static const char *fieldNames[] = {
        "taskId",
        "clientId",
        "serverId",
        "response",
        "critical",
        "createdAt",
        "deadlineAt",
        "workUnits",
        "queueSeconds",
        "responseBytes",
        "telemetry",
        "subscribe",
        "unsubscribe",
        "reportSequence",
        "reportGeneratedAt",
        "reportBusyUntil",
    };
    return (field >= 0 && field < 16) ? fieldNames[field] : nullptr;
}

int TaskChunkDescriptor::findField(const char *fieldName) const
{
    omnetpp::cClassDescriptor *base = getBaseClassDescriptor();
    int baseIndex = base ? base->getFieldCount() : 0;
    if (strcmp(fieldName, "taskId") == 0) return baseIndex + 0;
    if (strcmp(fieldName, "clientId") == 0) return baseIndex + 1;
    if (strcmp(fieldName, "serverId") == 0) return baseIndex + 2;
    if (strcmp(fieldName, "response") == 0) return baseIndex + 3;
    if (strcmp(fieldName, "critical") == 0) return baseIndex + 4;
    if (strcmp(fieldName, "createdAt") == 0) return baseIndex + 5;
    if (strcmp(fieldName, "deadlineAt") == 0) return baseIndex + 6;
    if (strcmp(fieldName, "workUnits") == 0) return baseIndex + 7;
    if (strcmp(fieldName, "queueSeconds") == 0) return baseIndex + 8;
    if (strcmp(fieldName, "responseBytes") == 0) return baseIndex + 9;
    if (strcmp(fieldName, "telemetry") == 0) return baseIndex + 10;
    if (strcmp(fieldName, "subscribe") == 0) return baseIndex + 11;
    if (strcmp(fieldName, "unsubscribe") == 0) return baseIndex + 12;
    if (strcmp(fieldName, "reportSequence") == 0) return baseIndex + 13;
    if (strcmp(fieldName, "reportGeneratedAt") == 0) return baseIndex + 14;
    if (strcmp(fieldName, "reportBusyUntil") == 0) return baseIndex + 15;
    return base ? base->findField(fieldName) : -1;
}

const char *TaskChunkDescriptor::getFieldTypeString(int field) const
{
    omnetpp::cClassDescriptor *base = getBaseClassDescriptor();
    if (base) {
        if (field < base->getFieldCount())
            return base->getFieldTypeString(field);
        field -= base->getFieldCount();
    }
    static const char *fieldTypeStrings[] = {
        "int",    // FIELD_taskId
        "int",    // FIELD_clientId
        "int",    // FIELD_serverId
        "bool",    // FIELD_response
        "bool",    // FIELD_critical
        "omnetpp::simtime_t",    // FIELD_createdAt
        "omnetpp::simtime_t",    // FIELD_deadlineAt
        "double",    // FIELD_workUnits
        "double",    // FIELD_queueSeconds
        "int",    // FIELD_responseBytes
        "bool",    // FIELD_telemetry
        "bool",    // FIELD_subscribe
        "bool",    // FIELD_unsubscribe
        "int",    // FIELD_reportSequence
        "omnetpp::simtime_t",    // FIELD_reportGeneratedAt
        "omnetpp::simtime_t",    // FIELD_reportBusyUntil
    };
    return (field >= 0 && field < 16) ? fieldTypeStrings[field] : nullptr;
}

const char **TaskChunkDescriptor::getFieldPropertyNames(int field) const
{
    omnetpp::cClassDescriptor *base = getBaseClassDescriptor();
    if (base) {
        if (field < base->getFieldCount())
            return base->getFieldPropertyNames(field);
        field -= base->getFieldCount();
    }
    switch (field) {
        default: return nullptr;
    }
}

const char *TaskChunkDescriptor::getFieldProperty(int field, const char *propertyName) const
{
    omnetpp::cClassDescriptor *base = getBaseClassDescriptor();
    if (base) {
        if (field < base->getFieldCount())
            return base->getFieldProperty(field, propertyName);
        field -= base->getFieldCount();
    }
    switch (field) {
        default: return nullptr;
    }
}

int TaskChunkDescriptor::getFieldArraySize(omnetpp::any_ptr object, int field) const
{
    omnetpp::cClassDescriptor *base = getBaseClassDescriptor();
    if (base) {
        if (field < base->getFieldCount())
            return base->getFieldArraySize(object, field);
        field -= base->getFieldCount();
    }
    TaskChunk *pp = omnetpp::fromAnyPtr<TaskChunk>(object); (void)pp;
    switch (field) {
        default: return 0;
    }
}

void TaskChunkDescriptor::setFieldArraySize(omnetpp::any_ptr object, int field, int size) const
{
    omnetpp::cClassDescriptor *base = getBaseClassDescriptor();
    if (base) {
        if (field < base->getFieldCount()){
            base->setFieldArraySize(object, field, size);
            return;
        }
        field -= base->getFieldCount();
    }
    TaskChunk *pp = omnetpp::fromAnyPtr<TaskChunk>(object); (void)pp;
    switch (field) {
        default: throw omnetpp::cRuntimeError("Cannot set array size of field %d of class 'TaskChunk'", field);
    }
}

const char *TaskChunkDescriptor::getFieldDynamicTypeString(omnetpp::any_ptr object, int field, int i) const
{
    omnetpp::cClassDescriptor *base = getBaseClassDescriptor();
    if (base) {
        if (field < base->getFieldCount())
            return base->getFieldDynamicTypeString(object,field,i);
        field -= base->getFieldCount();
    }
    TaskChunk *pp = omnetpp::fromAnyPtr<TaskChunk>(object); (void)pp;
    switch (field) {
        default: return nullptr;
    }
}

std::string TaskChunkDescriptor::getFieldValueAsString(omnetpp::any_ptr object, int field, int i) const
{
    omnetpp::cClassDescriptor *base = getBaseClassDescriptor();
    if (base) {
        if (field < base->getFieldCount())
            return base->getFieldValueAsString(object,field,i);
        field -= base->getFieldCount();
    }
    TaskChunk *pp = omnetpp::fromAnyPtr<TaskChunk>(object); (void)pp;
    switch (field) {
        case FIELD_taskId: return long2string(pp->getTaskId());
        case FIELD_clientId: return long2string(pp->getClientId());
        case FIELD_serverId: return long2string(pp->getServerId());
        case FIELD_response: return bool2string(pp->getResponse());
        case FIELD_critical: return bool2string(pp->getCritical());
        case FIELD_createdAt: return simtime2string(pp->getCreatedAt());
        case FIELD_deadlineAt: return simtime2string(pp->getDeadlineAt());
        case FIELD_workUnits: return double2string(pp->getWorkUnits());
        case FIELD_queueSeconds: return double2string(pp->getQueueSeconds());
        case FIELD_responseBytes: return long2string(pp->getResponseBytes());
        case FIELD_telemetry: return bool2string(pp->getTelemetry());
        case FIELD_subscribe: return bool2string(pp->getSubscribe());
        case FIELD_unsubscribe: return bool2string(pp->getUnsubscribe());
        case FIELD_reportSequence: return long2string(pp->getReportSequence());
        case FIELD_reportGeneratedAt: return simtime2string(pp->getReportGeneratedAt());
        case FIELD_reportBusyUntil: return simtime2string(pp->getReportBusyUntil());
        default: return "";
    }
}

void TaskChunkDescriptor::setFieldValueAsString(omnetpp::any_ptr object, int field, int i, const char *value) const
{
    omnetpp::cClassDescriptor *base = getBaseClassDescriptor();
    if (base) {
        if (field < base->getFieldCount()){
            base->setFieldValueAsString(object, field, i, value);
            return;
        }
        field -= base->getFieldCount();
    }
    TaskChunk *pp = omnetpp::fromAnyPtr<TaskChunk>(object); (void)pp;
    switch (field) {
        case FIELD_taskId: pp->setTaskId(string2long(value)); break;
        case FIELD_clientId: pp->setClientId(string2long(value)); break;
        case FIELD_serverId: pp->setServerId(string2long(value)); break;
        case FIELD_response: pp->setResponse(string2bool(value)); break;
        case FIELD_critical: pp->setCritical(string2bool(value)); break;
        case FIELD_createdAt: pp->setCreatedAt(string2simtime(value)); break;
        case FIELD_deadlineAt: pp->setDeadlineAt(string2simtime(value)); break;
        case FIELD_workUnits: pp->setWorkUnits(string2double(value)); break;
        case FIELD_queueSeconds: pp->setQueueSeconds(string2double(value)); break;
        case FIELD_responseBytes: pp->setResponseBytes(string2long(value)); break;
        case FIELD_telemetry: pp->setTelemetry(string2bool(value)); break;
        case FIELD_subscribe: pp->setSubscribe(string2bool(value)); break;
        case FIELD_unsubscribe: pp->setUnsubscribe(string2bool(value)); break;
        case FIELD_reportSequence: pp->setReportSequence(string2long(value)); break;
        case FIELD_reportGeneratedAt: pp->setReportGeneratedAt(string2simtime(value)); break;
        case FIELD_reportBusyUntil: pp->setReportBusyUntil(string2simtime(value)); break;
        default: throw omnetpp::cRuntimeError("Cannot set field %d of class 'TaskChunk'", field);
    }
}

omnetpp::cValue TaskChunkDescriptor::getFieldValue(omnetpp::any_ptr object, int field, int i) const
{
    omnetpp::cClassDescriptor *base = getBaseClassDescriptor();
    if (base) {
        if (field < base->getFieldCount())
            return base->getFieldValue(object,field,i);
        field -= base->getFieldCount();
    }
    TaskChunk *pp = omnetpp::fromAnyPtr<TaskChunk>(object); (void)pp;
    switch (field) {
        case FIELD_taskId: return pp->getTaskId();
        case FIELD_clientId: return pp->getClientId();
        case FIELD_serverId: return pp->getServerId();
        case FIELD_response: return pp->getResponse();
        case FIELD_critical: return pp->getCritical();
        case FIELD_createdAt: return pp->getCreatedAt().dbl();
        case FIELD_deadlineAt: return pp->getDeadlineAt().dbl();
        case FIELD_workUnits: return pp->getWorkUnits();
        case FIELD_queueSeconds: return pp->getQueueSeconds();
        case FIELD_responseBytes: return pp->getResponseBytes();
        case FIELD_telemetry: return pp->getTelemetry();
        case FIELD_subscribe: return pp->getSubscribe();
        case FIELD_unsubscribe: return pp->getUnsubscribe();
        case FIELD_reportSequence: return pp->getReportSequence();
        case FIELD_reportGeneratedAt: return pp->getReportGeneratedAt().dbl();
        case FIELD_reportBusyUntil: return pp->getReportBusyUntil().dbl();
        default: throw omnetpp::cRuntimeError("Cannot return field %d of class 'TaskChunk' as cValue -- field index out of range?", field);
    }
}

void TaskChunkDescriptor::setFieldValue(omnetpp::any_ptr object, int field, int i, const omnetpp::cValue& value) const
{
    omnetpp::cClassDescriptor *base = getBaseClassDescriptor();
    if (base) {
        if (field < base->getFieldCount()){
            base->setFieldValue(object, field, i, value);
            return;
        }
        field -= base->getFieldCount();
    }
    TaskChunk *pp = omnetpp::fromAnyPtr<TaskChunk>(object); (void)pp;
    switch (field) {
        case FIELD_taskId: pp->setTaskId(omnetpp::checked_int_cast<int>(value.intValue())); break;
        case FIELD_clientId: pp->setClientId(omnetpp::checked_int_cast<int>(value.intValue())); break;
        case FIELD_serverId: pp->setServerId(omnetpp::checked_int_cast<int>(value.intValue())); break;
        case FIELD_response: pp->setResponse(value.boolValue()); break;
        case FIELD_critical: pp->setCritical(value.boolValue()); break;
        case FIELD_createdAt: pp->setCreatedAt(value.doubleValue()); break;
        case FIELD_deadlineAt: pp->setDeadlineAt(value.doubleValue()); break;
        case FIELD_workUnits: pp->setWorkUnits(value.doubleValue()); break;
        case FIELD_queueSeconds: pp->setQueueSeconds(value.doubleValue()); break;
        case FIELD_responseBytes: pp->setResponseBytes(omnetpp::checked_int_cast<int>(value.intValue())); break;
        case FIELD_telemetry: pp->setTelemetry(value.boolValue()); break;
        case FIELD_subscribe: pp->setSubscribe(value.boolValue()); break;
        case FIELD_unsubscribe: pp->setUnsubscribe(value.boolValue()); break;
        case FIELD_reportSequence: pp->setReportSequence(omnetpp::checked_int_cast<int>(value.intValue())); break;
        case FIELD_reportGeneratedAt: pp->setReportGeneratedAt(value.doubleValue()); break;
        case FIELD_reportBusyUntil: pp->setReportBusyUntil(value.doubleValue()); break;
        default: throw omnetpp::cRuntimeError("Cannot set field %d of class 'TaskChunk'", field);
    }
}

const char *TaskChunkDescriptor::getFieldStructName(int field) const
{
    omnetpp::cClassDescriptor *base = getBaseClassDescriptor();
    if (base) {
        if (field < base->getFieldCount())
            return base->getFieldStructName(field);
        field -= base->getFieldCount();
    }
    switch (field) {
        default: return nullptr;
    };
}

omnetpp::any_ptr TaskChunkDescriptor::getFieldStructValuePointer(omnetpp::any_ptr object, int field, int i) const
{
    omnetpp::cClassDescriptor *base = getBaseClassDescriptor();
    if (base) {
        if (field < base->getFieldCount())
            return base->getFieldStructValuePointer(object, field, i);
        field -= base->getFieldCount();
    }
    TaskChunk *pp = omnetpp::fromAnyPtr<TaskChunk>(object); (void)pp;
    switch (field) {
        default: return omnetpp::any_ptr(nullptr);
    }
}

void TaskChunkDescriptor::setFieldStructValuePointer(omnetpp::any_ptr object, int field, int i, omnetpp::any_ptr ptr) const
{
    omnetpp::cClassDescriptor *base = getBaseClassDescriptor();
    if (base) {
        if (field < base->getFieldCount()){
            base->setFieldStructValuePointer(object, field, i, ptr);
            return;
        }
        field -= base->getFieldCount();
    }
    TaskChunk *pp = omnetpp::fromAnyPtr<TaskChunk>(object); (void)pp;
    switch (field) {
        default: throw omnetpp::cRuntimeError("Cannot set field %d of class 'TaskChunk'", field);
    }
}

}  // namespace v2x

namespace omnetpp {

}  // namespace omnetpp

