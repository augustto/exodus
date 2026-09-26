CREATE TABLE dbo.Orders (Id INT PRIMARY KEY, CustomerId INT);
GO
CREATE PROCEDURE dbo.usp_CloseOrder @id INT AS
    UPDATE dbo.Orders SET Closed = 1 WHERE Id = @id;
GO
