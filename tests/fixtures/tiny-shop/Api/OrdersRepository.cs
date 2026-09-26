using System.Data.SqlClient;

namespace Shop.Api
{
    public class OrdersRepository
    {
        private const string Open = "SELECT o.Id FROM dbo.Orders o JOIN dbo.Customers c ON c.Id = o.CustomerId";

        public void Close(int id)
        {
            Run("EXEC dbo.usp_CloseOrder @id", id);
        }

        private void Run(string sql, int id) { }
    }
}
