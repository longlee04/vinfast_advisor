import type { CustomerRecord, DemoUser } from "@/types/demo";

export const customerRecords: CustomerRecord[] = [
  { id: "customer-001", name: "Khách hàng #VF-101", email: "customer.101@example.com", phone: "09•• ••• 182", assignedAdvisor: "Advisor", needSummary: "Gia đình 5 người · ngân sách 800 triệu · có sạc tại nhà", lastActivity: "Hôm nay, 15:22", sessions: 3, status: "consulting" },
  { id: "customer-002", name: "Khách hàng #VF-102", email: "customer.102@example.com", phone: "09•• ••• 641", assignedAdvisor: "Advisor", needSummary: "Cá nhân · ưu tiên không gian · VF 7", lastActivity: "Hôm nay, 15:16", sessions: 2, status: "new" },
  { id: "customer-003", name: "Khách hàng #VF-103", email: "customer.103@example.com", phone: "09•• ••• 507", assignedAdvisor: "Advisor", needSummary: "Gia đình · đã chọn VF 6 Plus", lastActivity: "Hôm qua, 17:40", sessions: 5, status: "test_drive" },
  { id: "customer-004", name: "Khách hàng #VF-104", email: "customer.104@example.com", phone: "09•• ••• 933", assignedAdvisor: "Advisor", needSummary: "Đi làm nội đô · chi phí vận hành thấp", lastActivity: "03/08/2026", sessions: 1, status: "consulting" },
];

export const demoUsers: DemoUser[] = [
  { id: "usr-001", name: "Khách hàng Demo", email: "customer@gmail.com", role: "customer", status: "active", lastSeen: "Hôm nay, 15:22" },
  { id: "usr-002", name: "Tư vấn viên", email: "advisor@gmail.com", role: "advisor", status: "active", lastSeen: "Đang hoạt động" },
  { id: "usr-003", name: "Quản trị viên", email: "admin@gmail.com", role: "admin", status: "active", lastSeen: "Đang hoạt động" },
];
